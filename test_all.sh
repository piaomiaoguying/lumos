#!/bin/bash
set -e
cd "$(dirname "$0")"

# =============================================
# 虹明机电 CH34x USB 报警灯 控制脚本
# 协议: A0 + 地址 + 操作码 + 校验和(前3字节&0xFF)
# 地址: 01=黄 02=绿 03=红 09=蓝 00=全局
# 操作: 00=关 01=开 02=闪烁
# 绝不使用蜂鸣器(地址 04/05/06/07/0A)
# =============================================

VENV=".venv"
DEV=$(ls /dev/tty.usbserial-* 2>/dev/null | head -1)
if [ -z "$DEV" ]; then
    echo "[错误] 未找到 CH34x 设备，请先插入 USB"
    exit 1
fi

# 虚拟环境
if [ ! -d "$VENV" ]; then
    echo "[初始化] 创建虚拟环境..."
    python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"
if ! python -c "import serial" 2>/dev/null; then
    echo "[初始化] 安装 pyserial..."
    pip install pyserial -q
fi

# ---------- 发命令 ----------
send() {
    # $1=地址(hex)  $2=操作码(hex)  $3=描述
    local addr="$1" op="$2"
    local checksum=$(( (0xA0 + addr + op) & 0xFF ))
    python -c "
import serial
s = serial.Serial('$DEV', 9600, timeout=0.5)
s.write(bytes([0xA0, $addr, $op, $checksum]))
s.close()
" 2>/dev/null
    echo "  $3"
}

# ---------- 模式 ----------
show_help() {
    echo ""
    echo "用法: $0 [命令]"
    echo ""
    echo "  无参数      依次测试红→黄→绿→蓝（各1秒）"
    echo "  red         红灯常亮，Ctrl+C 退出"
    echo "  yellow      黄灯常亮，Ctrl+C 退出"
    echo "  green       绿灯常亮，Ctrl+C 退出"
    echo "  blue        蓝灯常亮，Ctrl+C 退出"
    echo "  red:blink   红灯闪烁，Ctrl+C 退出"
    echo "  yellow:blink 黄灯闪烁，Ctrl+C 退出"
    echo "  green:blink 绿灯闪烁，Ctrl+C 退出"
    echo "  blue:blink  蓝灯闪烁，Ctrl+C 退出"
    echo "  cycle       交通灯循环：红→黄→绿... Ctrl+C 退出"
    echo "  off         全部关闭"
    echo ""
}

cleanup() {
    echo ""
    send 0x00 0x00 "全部关闭"
    echo "退出"
    exit 0
}
trap cleanup INT

CMD="${1:-test}"

case "$CMD" in
    # ---- 常亮 ----
    red)
        echo "红灯常亮 (Ctrl+C 退出)"
        send 0x03 0x01 "红灯开"
        while true; do sleep 1; done
        ;;
    yellow)
        echo "黄灯常亮 (Ctrl+C 退出)"
        send 0x01 0x01 "黄灯开"
        while true; do sleep 1; done
        ;;
    green)
        echo "绿灯常亮 (Ctrl+C 退出)"
        send 0x02 0x01 "绿灯开"
        while true; do sleep 1; done
        ;;
    blue)
        echo "蓝灯常亮 (Ctrl+C 退出)"
        send 0x09 0x01 "蓝灯开"
        while true; do sleep 1; done
        ;;

    # ---- 闪烁 ----
    red:blink)
        echo "红灯闪烁 (Ctrl+C 退出)"
        send 0x03 0x02 "红灯闪烁"
        while true; do sleep 1; done
        ;;
    yellow:blink)
        echo "黄灯闪烁 (Ctrl+C 退出)"
        send 0x01 0x02 "黄灯闪烁"
        while true; do sleep 1; done
        ;;
    green:blink)
        echo "绿灯闪烁 (Ctrl+C 退出)"
        send 0x02 0x02 "绿灯闪烁"
        while true; do sleep 1; done
        ;;
    blue:blink)
        echo "蓝灯闪烁 (Ctrl+C 退出)"
        send 0x09 0x02 "蓝灯闪烁"
        while true; do sleep 1; done
        ;;

    # ---- 交通灯循环 ----
    cycle)
        echo "交通灯循环 (Ctrl+C 退出)"
        while true; do
            echo -n "  🔴"; send 0x03 0x01 ""; sleep 3
            echo -n "  🟡"; send 0x01 0x01 ""; sleep 1
            echo -n "  🟢"; send 0x02 0x01 ""; sleep 3
            echo -n "  🟡"; send 0x01 0x01 ""; sleep 1
        done
        ;;

    # ---- 全关 ----
    off)
        send 0x00 0x00 "全部关闭"
        ;;

    # ---- 帮助 ----
    help|--help|-h)
        show_help
        ;;

    # ---- 默认: 依次测试 ----
    *)
        echo "设备: $DEV"
        echo "依次测试：🔴 红灯 → 🟡 黄灯 → 🟢 绿灯 → 🔵 蓝灯"
        echo ""

        echo "=== 🔴 红灯 ==="
        send 0x03 0x01 "红灯开"
        sleep 1
        send 0x03 0x00 "红灯关"
        sleep 0.3

        echo "=== 🟡 黄灯 ==="
        send 0x01 0x01 "黄灯开"
        sleep 1
        send 0x01 0x00 "黄灯关"
        sleep 0.3

        echo "=== 🟢 绿灯 ==="
        send 0x02 0x01 "绿灯开"
        sleep 1
        send 0x02 0x00 "绿灯关"
        sleep 0.3

        echo "=== 🔵 蓝灯 ==="
        send 0x09 0x01 "蓝灯开"
        sleep 1
        send 0x09 0x00 "蓝灯关"

        echo ""
        echo "全部测试完毕 ✅"
        ;;
esac
