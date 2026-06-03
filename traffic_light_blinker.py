#!/usr/bin/env python3
# 首选项目虚拟环境运行: .venv/bin/python
"""软件呼吸灯 — 慢节奏闪烁替代硬件快闪

由 traffic_light_hook.py 管理生命周期。
通过 blink_target 文件与 hook 通信：文件内容变为非自身颜色时自动退出。
"""

import os
import sys
import time
from pathlib import Path

STATE_DIR = Path.home() / ".claude/state/traffic-light"
TARGET_FILE = STATE_DIR / "blink_target"
PID_FILE = STATE_DIR / "blinker.pid"

# 呼吸节奏
ON_SEC = 2.0
OFF_SEC = 1.0


def main():
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <color>", file=sys.stderr)
        sys.exit(1)

    color = sys.argv[1]

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from traffic_light_controller import TrafficLightController

    ctrl = TrafficLightController()
    if not ctrl.available:
        sys.exit(0)

    # 写入 PID
    PID_FILE.write_text(str(os.getpid()))

    try:
        while True:
            # 检查目标文件：如果颜色变了或没了，退出
            try:
                target = TARGET_FILE.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                target = ""
            if target != color:
                break

            # --- 亮 ---
            ctrl.set_light(color, "on")
            for _ in range(int(ON_SEC * 10)):
                time.sleep(0.1)
                try:
                    if TARGET_FILE.read_text(encoding="utf-8").strip() != color:
                        break
                except FileNotFoundError:
                    break
            else:
                # --- 灭 ---
                ctrl.set_light(color, "off")
                for _ in range(int(OFF_SEC * 10)):
                    time.sleep(0.1)
                    try:
                        if TARGET_FILE.read_text(encoding="utf-8").strip() != color:
                            break
                    except FileNotFoundError:
                        break
                continue
            break

    finally:
        # 退出前关灯
        ctrl.set_light(color, "off")
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
