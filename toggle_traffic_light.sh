#!/bin/bash
set -e
# =============================================
# 交通灯 Hook 开关脚本
# 用法:
#   ./toggle_traffic_light.sh        # 自动检测设备
#   ./toggle_traffic_light.sh on     # 强制启用
#   ./toggle_traffic_light.sh off    # 强制禁用
#   ./toggle_traffic_light.sh status # 查看状态
#
# 说明:
#   SessionStart 事件会自动检测设备并刷新哨兵文件，
#   此脚本用于手动覆盖或在会话中途切换。
# =============================================

SENTINEL="$HOME/.claude/state/traffic-light/disabled"

enable_hook() {
    if [ -f "$SENTINEL" ]; then
        rm "$SENTINEL"
        echo "✅ 已启用交通灯 hook"
    else
        echo "ℹ️  已经是启用状态"
    fi
}

disable_hook() {
    if [ ! -f "$SENTINEL" ]; then
        mkdir -p "$(dirname "$SENTINEL")"
        touch "$SENTINEL"
        echo "❌ 已禁用交通灯 hook"
    else
        echo "ℹ️  已经是禁用状态"
    fi
}

device_exists() {
    ls /dev/tty.usbserial-* >/dev/null 2>&1
}

CMD="${1:-auto}"

case "$CMD" in
    on)
        enable_hook
        ;;
    off)
        disable_hook
        ;;
    status)
        if [ -f "$SENTINEL" ]; then
            echo "状态: 🔴 已禁用 (哨兵文件存在)"
            echo "       SessionStart 会自动检测设备，如有设备会重新启用"
        else
            echo "状态: 🟢 已启用 (hook 正常执行)"
        fi
        ;;
    auto|*)
        if device_exists; then
            echo "🔌 检测到串口设备 → 启用"
            enable_hook
        else
            echo "🔌 未检测到串口设备 → 禁用"
            disable_hook
        fi
        ;;
esac