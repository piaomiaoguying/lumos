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

if [ ! -d "$VENV" ]; then
    python3 -m venv "$VENV"
fi
source "$VENV/bin/activate"
if ! python -c "import serial" 2>/dev/null; then
    pip install pyserial -q
fi

send() {
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

cleanup() {
    echo ""
    send 0x00 0x00 "全部关闭"
    echo "已退出"
    exit 0
}
trap cleanup INT

show_menu() {
    echo ""
    echo "═══════════════════════════════════"
    echo "  CH34x USB 报警灯 - 命令菜单"
    echo "═══════════════════════════════════"
    echo ""
    echo "  常亮:"
    echo "    1) 🔴 红灯常亮"
    echo "    2) 🟡 黄灯常亮"
    echo "    3) 🟢 绿灯常亮"
    echo "    4) 🔵 蓝灯常亮"
    echo ""
    echo "  闪烁:"
    echo "    5) 🔴 红灯闪烁"
    echo "    6) 🟡 黄灯闪烁"
    echo "    7) 🟢 绿灯闪烁"
    echo "    8) 🔵 蓝灯闪烁"
    echo ""
    echo "  其他:"
    echo "    9) 🚦 交通灯循环"
    echo "   10) ⚫ 全部关闭"
    echo ""
    echo "═══════════════════════════════════"
}

CMD="${1}"

# 如果传了参数，直接执行
if [ -n "$CMD" ]; then
    case "$CMD" in
        red)            echo "红灯常亮 (Ctrl+C 退出)"; send 0x03 0x01 "红灯开"; while true; do sleep 1; done ;;
        yellow)         echo "黄灯常亮 (Ctrl+C 退出)"; send 0x01 0x01 "黄灯开"; while true; do sleep 1; done ;;
        green)          echo "绿灯常亮 (Ctrl+C 退出)"; send 0x02 0x01 "绿灯开"; while true; do sleep 1; done ;;
        blue)           echo "蓝灯常亮 (Ctrl+C 退出)"; send 0x09 0x01 "蓝灯开"; while true; do sleep 1; done ;;
        red:blink)      echo "红灯闪烁 (Ctrl+C 退出)"; send 0x03 0x02 "红灯闪烁"; while true; do sleep 1; done ;;
        yellow:blink)   echo "黄灯闪烁 (Ctrl+C 退出)"; send 0x01 0x02 "黄灯闪烁"; while true; do sleep 1; done ;;
        green:blink)    echo "绿灯闪烁 (Ctrl+C 退出)"; send 0x02 0x02 "绿灯闪烁"; while true; do sleep 1; done ;;
        blue:blink)     echo "蓝灯闪烁 (Ctrl+C 退出)"; send 0x09 0x02 "蓝灯闪烁"; while true; do sleep 1; done ;;
        cycle)
            echo "交通灯循环 (Ctrl+C 退出)"
            while true; do
                echo -n "  🔴"; send 0x03 0x01 ""; sleep 3
                echo -n "  🟡"; send 0x01 0x01 ""; sleep 1
                echo -n "  🟢"; send 0x02 0x01 ""; sleep 3
                echo -n "  🟡"; send 0x01 0x01 ""; sleep 1
            done
            ;;
        off)            send 0x00 0x00 "全部关闭" ;;
        *)              echo "未知命令: $CMD" ;;
    esac
    exit 0
fi

# 无参数 → 显示菜单让用户选择
show_menu
echo -n "请输入数字 (1-10): "
read -r CHOICE

case "$CHOICE" in
    1)  echo "红灯常亮 (Ctrl+C 退出)"
        send 0x03 0x01 "红灯开"
        while true; do sleep 1; done
        ;;
    2)  echo "黄灯常亮 (Ctrl+C 退出)"
        send 0x01 0x01 "黄灯开"
        while true; do sleep 1; done
        ;;
    3)  echo "绿灯常亮 (Ctrl+C 退出)"
        send 0x02 0x01 "绿灯开"
        while true; do sleep 1; done
        ;;
    4)  echo "蓝灯常亮 (Ctrl+C 退出)"
        send 0x09 0x01 "蓝灯开"
        while true; do sleep 1; done
        ;;
    5)  echo "红灯闪烁 (Ctrl+C 退出)"
        send 0x03 0x02 "红灯闪烁"
        while true; do sleep 1; done
        ;;
    6)  echo "黄灯闪烁 (Ctrl+C 退出)"
        send 0x01 0x02 "黄灯闪烁"
        while true; do sleep 1; done
        ;;
    7)  echo "绿灯闪烁 (Ctrl+C 退出)"
        send 0x02 0x02 "绿灯闪烁"
        while true; do sleep 1; done
        ;;
    8)  echo "蓝灯闪烁 (Ctrl+C 退出)"
        send 0x09 0x02 "蓝灯闪烁"
        while true; do sleep 1; done
        ;;
    9)  echo "交通灯循环 (Ctrl+C 退出)"
        while true; do
            echo -n "  🔴"; send 0x03 0x01 ""; sleep 3
            echo -n "  🟡"; send 0x01 0x01 ""; sleep 1
            echo -n "  🟢"; send 0x02 0x01 ""; sleep 3
            echo -n "  🟡"; send 0x01 0x01 ""; sleep 1
        done
        ;;
    10) send 0x00 0x00 "全部关闭" ;;
    *)  echo "无效选择，请输入 1-10" ; exit 1 ;;
esac
