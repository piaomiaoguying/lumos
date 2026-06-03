#!/usr/bin/env python3
# 首选项目虚拟环境运行: .venv/bin/python
"""虹明机电 USB 串口报警灯 核心控制库

协议: A0 + 地址(1B) + 操作码(1B) + 校验和(1B)
地址: 黄 0x01, 绿 0x02, 红 0x03, 蓝 0x09
操作: 关 0x00, 常亮 0x01, 闪烁 0x02
校验和 = (A0 + 地址 + 操作码) & 0xFF
命令间隔 >= 100ms
"""

import glob
import threading
import time
import serial


class TrafficLightController:
    """USB 串口报警灯控制器，线程安全。"""

    # 硬件协议常量
    HEADER = 0xA0
    ADDR = {
        "yellow": 0x01,
        "green": 0x02,
        "red": 0x03,
        "blue": 0x09,
        "all": 0x00,
    }
    OPCODE = {
        "off": 0x00,
        "on": 0x01,
        "blink": 0x02,
    }

    def __init__(self, device: str | None = None):
        """初始化控制器。

        Args:
            device: 串口设备路径，为 None 时自动检测。
        """
        self._device = device or self.detect_device()
        self._lock = threading.Lock()
        self._last_send: float = 0.0

    @staticmethod
    def detect_device() -> str | None:
        """自动发现 CH34x USB 串口设备。"""
        devices = glob.glob("/dev/tty.usbserial-*")
        return devices[0] if devices else None

    @property
    def available(self) -> bool:
        """设备是否可用。"""
        return self._device is not None

    @property
    def device(self) -> str | None:
        """当前设备路径。"""
        return self._device

    def send(self, addr: int, opcode: int) -> None:
        """发送原始命令帧。

        Args:
            addr: 地址码 (0x01-0x09 或 0x00 全局)
            opcode: 操作码 (0x00 关, 0x01 常亮, 0x02 闪烁)
        """
        if not self._device:
            return
        with self._lock:
            # 100ms 间隔保护
            elapsed = time.monotonic() - self._last_send
            if elapsed < 0.1:
                time.sleep(0.1 - elapsed)
            checksum = (self.HEADER + addr + opcode) & 0xFF
            try:
                with serial.Serial(self._device, 9600, timeout=0.5) as s:
                    s.write(bytes([self.HEADER, addr, opcode, checksum]))
            except serial.SerialException:
                pass
            self._last_send = time.monotonic()

    def set_light(self, color: str, mode: str) -> None:
        """控制指定颜色的灯。

        Args:
            color: 颜色名 ("red", "yellow", "green", "blue")
            mode: 模式 ("off", "on", "blink")
        """
        if color not in self.ADDR or mode not in self.OPCODE:
            return
        self.send(self.ADDR[color], self.OPCODE[mode])

    def all_off(self) -> None:
        """关闭所有灯（使用全局地址 0x00）。"""
        self.send(self.ADDR["all"], self.OPCODE["off"])

    def apply_state(self, status: str) -> None:
        """根据状态名设置灯色和模式。

        Args:
            status: 状态名 ("off", "working", "standby", "waiting_user", "need_user", "error")
        """
        mapping = {
            "off":           ("all",    "off"),
            "working":       ("green",  "blink"),
            "standby":       ("green",  "on"),
            "waiting_user":  ("yellow", "on"),
            "need_user":     ("yellow", "blink"),
            "error":         ("red",    "blink"),
        }
        if status not in mapping:
            return
        color, mode = mapping[status]
        if color == "all":
            self.all_off()
        else:
            self.set_light(color, mode)

    def test_all(self) -> None:
        """依次测试四色 × 三种模式（常亮→闪烁→关闭）。"""
        if not self._device:
            print("[跳过] 未检测到 USB 设备")
            return
        print(f"设备: {self._device}")
        print("依次测试：🔴 红 → 🟡 黄 → 🟢 绿 → 🔵 蓝\n")

        for name, color in [("红", "red"), ("黄", "yellow"), ("绿", "green"), ("蓝", "blue")]:
            print(f"=== 🔴🟡🟢🔵 {name}灯 ===".replace("🔴🟡🟢🔵", {"红": "🔴", "黄": "🟡", "绿": "🟢", "蓝": "🔵"}[name]))
            self.set_light(color, "on")
            print(f"  {name}灯常亮")
            time.sleep(0.8)
            self.set_light(color, "blink")
            print(f"  {name}灯闪烁")
            time.sleep(0.8)
            self.set_light(color, "off")
            print(f"  {name}灯关闭")
            time.sleep(0.3)

        self.all_off()
        print("\n全部测试完毕 ✅")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="虹明机电 USB 报警灯控制")
    parser.add_argument("--test-all", action="store_true", help="依次测试所有灯色")
    parser.add_argument("--device", type=str, default=None, help="串口设备路径")
    parser.add_argument("--color", type=str, choices=["red", "yellow", "green", "blue", "all"],
                        help="灯色")
    parser.add_argument("--mode", type=str, choices=["off", "on", "blink"],
                        help="模式")
    args = parser.parse_args()

    ctrl = TrafficLightController(args.device)

    if args.test_all:
        ctrl.test_all()
    elif args.color and args.mode:
        ctrl.set_light(args.color, args.mode)
    else:
        parser.print_help()
