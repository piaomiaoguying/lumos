#!/usr/bin/env python3
# 首选项目虚拟环境运行: .venv/bin/python
"""traffic-light-hook — Claude Code 全局 Hook 脚本

将 Claude Code 运行状态映射到物理红绿灯（虹明机电 USB 串口报警灯）。

调用方式（由 Claude Code hook 触发）:
    python3 traffic_light_hook.py <event> <status> <priority>

架构：纯 hook 驱动，无守护进程。
每次 hook 触发时：
  0. SessionStart 时自动检测设备，刷新哨兵文件；其他事件读哨兵文件快速退出
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
import glob
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
DISABLED_FILE = STATE_DIR / "disabled"

# 分状态 TTL（秒）
TTL: dict[str, float] = {
    "working": 15,
    "standby": 120,
    "waiting_user": 300,
}

# 闪烁状态——需要人工介入，不能被其他实例的低优先级状态覆盖
BLINK_STATES: set[str] = {"need_user", "error"}

# 状态 → (颜色, 模式)
# 模式 "on"/"off" 直接发串口，"blink" 启动软件呼吸灯
STATE_MAP: dict[str, tuple[str, str]] = {
    "off":           ("all",    "off"),
    "working":       ("green",  "blink"),
    "standby":       ("blue",   "on"),
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

# 日志配置
LOG_FILE = STATE_DIR / "hook.log"
NO_LOG_FILE = STATE_DIR / "no-log"
MAX_LOG_SIZE = 100 * 1024  # 100KB


def _log(session_id: str, event: str, status: str, result: str):
    """追加一行日志，超限时自动截断。失败不影响主逻辑。"""
    if NO_LOG_FILE.exists():
        return
    try:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        short_id = session_id[:8]
        line = f"{now} {short_id} {event} {status} {result}\n"
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
        if LOG_FILE.stat().st_size > MAX_LOG_SIZE:
            lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
            LOG_FILE.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
    except OSError:
        pass


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
                continue          # 不在 TTL 表里的状态不清理（need_user / error）
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


def _aggregate(now: float) -> tuple[str, int, str]:
    """扫描所有实例文件，返回 最后更新 的实例状态。

    后触发者胜——不按优先级聚合，谁最后写文件就听谁的。
    无有效实例时返回 ("off", sys.maxsize, "")。
    """
    best_status = "off"
    best_priority = sys.maxsize
    best_session_id = ""
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
                best_session_id = data.get("session_id", "")
    except FileNotFoundError:
        pass
    return best_status, best_priority, best_session_id


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

    每次切换状态时：
      1. 先杀掉旧 blinker 进程
      2. 关闭所有灯（避免上一状态的颜色残留）
      3. 再设置新状态

    - "off" 模式 → 直接发串口命令
    - "blink" 模式 → 启动软件呼吸灯进程（常驻）
    """
    if status not in STATE_MAP:
        return

    color, mode = STATE_MAP[status]
    ctrl = _get_controller()
    if not ctrl.available:
        return

    # 先清理旧状态：杀 blinker + 全关，避免颜色残留
    _kill_blinker()
    ctrl.all_off()
    time.sleep(0.15)

    if mode == "blink":
        _start_blinker(color)
    elif color != "all":
        ctrl.set_light(color, mode)


# ── 主入口 ────────────────────────────────────────────

def main():
    if len(sys.argv) < 4:
        print(f"用法: {sys.argv[0]} <event> <status> <priority>", file=sys.stderr)
        sys.exit(0)

    event = sys.argv[1]
    status = sys.argv[2]
    priority = int(sys.argv[3])

    # 提前获取 session_id，日志和 disabled 路径也需要
    session_id = _get_session_id()

    # SessionStart 时自动检测设备，刷新哨兵文件
    if event == "SessionStart":
        if glob.glob("/dev/tty.usbserial-*"):
            DISABLED_FILE.unlink(missing_ok=True)
        else:
            DISABLED_FILE.parent.mkdir(parents=True, exist_ok=True)
            DISABLED_FILE.touch()

    # 哨兵文件存在 → 已禁用，直接退出
    if DISABLED_FILE.exists():
        _log(session_id, event, status, "disabled")
        sys.exit(0)
    project = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    _ensure_dirs()

    # ── flock（带重试，避免多实例竞争时静默丢弃） ────
    lock_fd = None
    try:
        lock_fd = open(LOCK_FILE, "a+")
    except OSError:
        lock_fd = None

    acquired = False
    if lock_fd is not None:
        for _attempt in range(3):
            try:
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (BlockingIOError, OSError):
                time.sleep(0.3)

    if not acquired:
        _log(session_id, event, status, "flock_busy:skipped")
        if lock_fd:
            lock_fd.close()
        sys.exit(0)

    try:
        now = time.time()

        # 0) 清理过期（在写本实例之前，确保不会读到过期数据）
        _cleanup_expired(now)

        # 1) 本实例
        if event == "SessionEnd":
            _delete_instance(session_id)
        else:
            _write_instance(session_id, status, priority, project)

        # 1.5) 日志：记录 SessionStart 的设备检测结果
        if event == "SessionStart":
            _log(session_id, event, status, "auto-detect:enabled")

        # 2) 聚合（后触发者胜）
        best_status, best_priority, aggregated_session_id = _aggregate(now)

        # 2.5) 闪烁锁：闪烁状态一旦确立，只能被同一实例、更高优先级闪烁、或已死实例覆盖
        prev = _read_current_state()
        if prev and prev.get("status") in BLINK_STATES:
            owner_id = prev.get("owner_session_id", "")
            owner_file = INSTANCES_DIR / f"{owner_id}.json"
            if owner_file.exists():
                # 锁主还活着 → 只有同一实例或更高优先级闪烁才能覆盖
                if aggregated_session_id == owner_id:
                    pass  # 放行：同一实例
                elif aggregated_session_id != "" and best_status in BLINK_STATES and best_priority < prev.get("priority", sys.maxsize):
                    pass  # 放行：更高优先级闪烁升级（error 覆盖 need_user）
                else:
                    _log(session_id, event, status, f"blink-lock:rejected_{best_status}")
                    best_status = prev["status"]
                    best_priority = prev["priority"]
                    aggregated_session_id = owner_id  # 保持原所有者不变
            # else: 锁主已死（SessionEnd 删了文件）→ 放行

        # 3) Debounce: 本实例刚切到 standby，但之前是 working → 保持 working
        if best_status == "standby":
            prev = _read_current_state()
            if prev and prev.get("status") == "working":
                working_since = prev.get("working_since", 0)
                if now - working_since < DEBOUNCE_WORKING:
                    _log(session_id, event, status, "debounce:kept_working")
                    best_status = "working"
                    best_priority = 4

        # 4) 状态没变 → 跳过
        prev = _read_current_state()
        if prev and prev.get("status") == best_status:
            _log(session_id, event, status, "same")
            raise SystemExit(0)

        # 5) 控制灯
        _apply_light(best_status)

        # 6) 记录状态 + 日志
        prev_status = prev.get("status", "off") if prev else "off"
        color, mode = STATE_MAP.get(best_status, ("?", "?"))
        _log(session_id, event, status, f"{prev_status}→{best_status}:{color}_{mode}")

        state_record = {
            "status": best_status,
            "priority": best_priority,
            "updated_at": now,
        }
        if best_status in BLINK_STATES:
            state_record["owner_session_id"] = aggregated_session_id
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
