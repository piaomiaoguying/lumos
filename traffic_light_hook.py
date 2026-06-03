#!/usr/bin/env python3
# 首选项目虚拟环境运行: .venv/bin/python
"""traffic-light-hook — Claude Code 全局 Hook 脚本

将 Claude Code 运行状态映射到物理红绿灯（虹明机电 USB 串口报警灯）。

调用方式（由 Claude Code hook 触发）:
    python3 traffic_light_hook.py <event> <status> <priority>

架构：纯 hook 驱动，无守护进程。
每次 hook 触发时：
  1. flock 全局锁（防多实例同时写串口）
  2. 扫描 ~/.claude/state/traffic-light/instances/ → 清理过期文件
  3. 写入/更新本实例状态文件
  4. 取最后更新的实例状态（后触发者胜）
  5. 状态有变化 → 控制灯
     - 常亮/常灭 → 直接发串口命令，杀掉 blinker 进程
     - 闪烁 → 启动软件 blinker（亮1.5s灭0.5s），常驻直到状态切换
  6. 释放锁，退出
"""

import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# ── 配置 ───────────────────────────────────────────────

STATE_DIR = Path.home() / ".claude/state/traffic-light"
INSTANCES_DIR = STATE_DIR / "instances"
LOCK_FILE = STATE_DIR / "lock"
CURRENT_STATE_FILE = STATE_DIR / "current_state"
BLINK_TARGET = STATE_DIR / "blink_target"
PID_FILE = STATE_DIR / "blinker.pid"

# 分状态 TTL（秒）
TTL: dict[str, float] = {
    "working": 15,
    "standby": 120,
    "waiting_user": 300,
    "need_user": 300,
    "error": 300,
}

# 状态 → (颜色, 模式)
# 模式 "on"/"off" 直接发串口，"blink" 启动软件呼吸灯
STATE_MAP: dict[str, tuple[str, str]] = {
    "off":           ("all",    "off"),
    "working":       ("green",  "blink"),
    "standby":       ("green",  "on"),
    "waiting_user":  ("yellow", "on"),
    "need_user":     ("yellow", "blink"),
    "error":         ("red",    "blink"),
}

# Debounce：从 working 切到 standby 的最小间隔（秒）
DEBOUNCE_WORKING = 3.0

# 本项目根目录
PROJECT_DIR = Path(__file__).resolve().parent
BLINKER_SCRIPT = PROJECT_DIR / "traffic_light_blinker.py"
VENV_PYTHON = PROJECT_DIR / ".venv/bin/python"

_controller: object | None = None


def _get_controller():
    global _controller
    if _controller is None:
        from traffic_light_controller import TrafficLightController
        _controller = TrafficLightController()
    return _controller


def _ensure_dirs():
    INSTANCES_DIR.mkdir(parents=True, exist_ok=True)


def _get_session_id() -> str:
    try:
        raw = sys.stdin.read()
        if raw and raw.strip():
            data = json.loads(raw)
            sid = data.get("session_id") or data.get("sessionId")
            if sid:
                return str(sid)
    except (json.JSONDecodeError, OSError):
        pass
    env_sid = os.environ.get("CLAUDE_SESSION_ID")
    if env_sid:
        return env_sid
    return f"ppid{os.getppid()}-{int(time.time() * 1000)}"


def _cleanup_expired(now: float):
    try:
        for path in INSTANCES_DIR.iterdir():
            if not path.suffix == ".json":
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                path.unlink(missing_ok=True)
                continue
            max_age = TTL.get(data.get("status", ""))
            if max_age is None:
                max_age = 120
            if now - data.get("updated_at", 0) > max_age:
                path.unlink(missing_ok=True)
    except FileNotFoundError:
        pass


def _write_instance(session_id: str, status: str, priority: int, project: str):
    (INSTANCES_DIR / f"{session_id}.json").write_text(
        json.dumps({
            "session_id": session_id,
            "project": project,
            "status": status,
            "priority": priority,
            "updated_at": time.time(),
        }, ensure_ascii=False),
        encoding="utf-8",
    )


def _delete_instance(session_id: str):
    (INSTANCES_DIR / f"{session_id}.json").unlink(missing_ok=True)


def _read_current_state() -> dict | None:
    try:
        return json.loads(CURRENT_STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_current_state(state: dict):
    CURRENT_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def _aggregate(now: float) -> tuple[str, int]:
    """扫描所有实例文件，返回 最后更新 的实例状态。

    后触发者胜——不按优先级聚合，谁最后写文件就听谁的。
    无有效实例时返回 ("off", sys.maxsize)。
    """
    best_status = "off"
    best_priority = sys.maxsize
    best_updated = 0.0

    try:
        for path in INSTANCES_DIR.iterdir():
            if not path.suffix == ".json":
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            updated = data.get("updated_at", 0)
            if updated > best_updated:
                best_updated = updated
                best_status = data.get("status", "off")
                best_priority = data.get("priority", sys.maxsize)
    except FileNotFoundError:
        pass
    return best_status, best_priority


def _kill_blinker():
    """杀死正在运行的 blinker 进程。"""
    try:
        old_pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        old_pid = None
    if old_pid:
        try:
            os.kill(old_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        subprocess.run(
            ["pkill", "-f", "traffic_light_blinker.py"],
            capture_output=True,
            timeout=2,
        )
    except Exception:
        pass
    PID_FILE.unlink(missing_ok=True)
    BLINK_TARGET.unlink(missing_ok=True)


def _start_blinker(color: str):
    """启动软件呼吸灯进程。先杀掉旧的再启动。"""
    _kill_blinker()
    BLINK_TARGET.write_text(color)
    subprocess.Popen(
        [str(VENV_PYTHON), str(BLINKER_SCRIPT), color],
        start_new_session=True,  # 脱离 Claude Code 进程树
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.2)


def _apply_light(status: str):
    """根据聚合后的状态控制灯。

    - "off" 模式 → 直接发串口命令
    - "blink" 模式 → 启动软件呼吸灯进程（常驻）
    """
    if status not in STATE_MAP:
        return

    color, mode = STATE_MAP[status]
    ctrl = _get_controller()
    if not ctrl.available:
        return

    if mode == "blink":
        _start_blinker(color)
    else:
        _kill_blinker()
        if color == "all":
            ctrl.all_off()
        else:
            ctrl.set_light(color, mode)


# ── 主入口 ────────────────────────────────────────────

def main():
    if len(sys.argv) < 4:
        print(f"用法: {sys.argv[0]} <event> <status> <priority>", file=sys.stderr)
        sys.exit(0)

    event = sys.argv[1]
    status = sys.argv[2]
    priority = int(sys.argv[3])

    session_id = _get_session_id()
    project = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    _ensure_dirs()

    # ── flock ───────────────────────────────────────
    lock_fd = None
    try:
        lock_fd = open(LOCK_FILE, "a+")
    except OSError:
        lock_fd = None

    acquired = False
    if lock_fd is not None:
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except (BlockingIOError, OSError):
            acquired = False

    if not acquired:
        if lock_fd:
            lock_fd.close()
        sys.exit(0)

    try:
        now = time.time()

        # 1) 清理过期
        _cleanup_expired(now)

        # 2) 本实例
        if event == "SessionEnd":
            _delete_instance(session_id)
        else:
            _write_instance(session_id, status, priority, project)

        # 3) 聚合（后触发者胜）
        best_status, best_priority = _aggregate(now)

        # 4) Debounce: 本实例刚切到 standby，但之前是 working → 保持 working
        if best_status == "standby":
            prev = _read_current_state()
            if prev and prev.get("status") == "working":
                working_since = prev.get("working_since", 0)
                if now - working_since < DEBOUNCE_WORKING:
                    best_status = "working"
                    best_priority = 4

        # 5) 状态没变 → 跳过
        prev = _read_current_state()
        if prev and prev.get("status") == best_status:
            raise SystemExit(0)

        # 6) 控制灯
        _apply_light(best_status)

        # 7) 记录状态
        state_record = {
            "status": best_status,
            "priority": best_priority,
            "updated_at": now,
        }
        if best_status == "working":
            state_record["working_since"] = prev.get("working_since", now) if prev else now
        _write_current_state(state_record)

    except SystemExit:
        pass
    finally:
        try:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        if lock_fd:
            lock_fd.close()


if __name__ == "__main__":
    main()
