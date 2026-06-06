#!/bin/bash
set -e
# =============================================
# 交通灯 hook 一键安装脚本
#
# 用法: ./install.sh          # 安装
#       python3 install.py --dry-run  # 预览 hook 配置
#
# 做了什么:
#   1. 创建虚拟环境，安装 pyserial
#   2. 创建符号链接 ~/.claude/scripts/traffic-light-hook
#   3. 安全合并 hook 到 ~/.claude/settings.json（不干扰已有配置）
#   4. 创建运行时目录
# =============================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
SETTINGS_DIR="$HOME/.claude/scripts"
STATE_DIR="$HOME/.claude/state/traffic-light"
HOOK_SYMLINK="$SETTINGS_DIR/traffic-light-hook"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

step()  { echo -e "${BLUE}→${NC} $1"; }
ok()    { echo -e "${GREEN}✓${NC} $1"; }

# ── 1. 虚拟环境 ──────────────────────────────────────
step "创建 Python 虚拟环境..."
if [ ! -f "$VENV_DIR/bin/python" ]; then
    python3 -m venv "$VENV_DIR"
    ok "虚拟环境创建完成"
else
    ok "虚拟环境已存在"
fi

step "安装 pyserial..."
"$VENV_DIR/bin/pip" install --quiet pyserial
ok "pyserial 已安装"

# ── 2. 符号链接 ──────────────────────────────────────
step "创建符号链接..."
mkdir -p "$SETTINGS_DIR"
ln -sf "$SCRIPT_DIR/traffic_light_hook.py" "$HOOK_SYMLINK"
ok "符号链接: $HOOK_SYMLINK → $SCRIPT_DIR/traffic_light_hook.py"

# ── 3. settings.json ─────────────────────────────────
step "合并 hook 到 ~/.claude/settings.json..."
"$VENV_DIR/bin/python" "$SCRIPT_DIR/install.py"
ok "hook 配置完成"

# ── 4. 运行时目录 ────────────────────────────────────
step "创建运行时目录..."
mkdir -p "$STATE_DIR/instances"
ok "运行时目录: $STATE_DIR"

# ── 5. 完成 ─────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " 🚦 安装完成"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  下次启动新的 Claude Code 会话时生效"
echo ""
echo "  开关工具:"
echo "    ./toggle_traffic_light.sh on      强制启用"
echo "    ./toggle_traffic_light.sh off     强制禁用"
echo "    ./toggle_traffic_light.sh status  查看状态"
echo ""
echo "  测试灯:"
echo "    .venv/bin/python traffic_light_controller.py --test-all"
echo ""
echo "  查看日志:"
echo "    ./toggle_traffic_light.sh log-on"
echo "    tail -f ~/.claude/state/traffic-light/hook.log"
