#!/usr/bin/env python3
"""install.py — 安装 Claude Code 交通灯 hook 到 settings.json

将 traffic-light hook 安全合并到 ~/.claude/settings.json：
- 保留用户已有的所有配置（其他 hook、env、permissions 等）
- 每个 traffic-light hook 放在独立的 group 中，不干扰其他 hook
- 重复运行安全（自动更新路径）

用法:
    python3 install.py          # 安装
    python3 install.py --dry-run  # 预览将要写入的 hook 配置
"""

import json
import os
import sys
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv or "--dryrun" in sys.argv

# ── 配置 ───────────────────────────────────────────────

# 自动探测项目目录（无论从哪里执行 install.py）
PROJECT_DIR = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_DIR / ".venv/bin/python"
HOOK_SCRIPT = Path.home() / ".claude/scripts/traffic-light-hook"
SETTINGS_FILE = Path.home() / ".claude/settings.json"

# 定义 traffic-light 的 8 类 hook 事件，每个事件一个独立 group
# 注意：每个事件的 group 只包含 traffic-light hook 本身
HOOK_DEFS = [
    # (事件名, matcher, 状态, 优先级)
    ("SessionStart",     None,               "standby",     5),
    ("UserPromptSubmit", None,               "working",     4),
    ("Stop",             None,               "standby",     5),
    ("PermissionRequest",None,               "need_user",   2),
    ("Notification",     "permission_prompt", "need_user",  2),
    ("Notification",     "idle_prompt",       "waiting_user", 3),
    ("Elicitation",      None,               "waiting_user", 3),
    ("StopFailure",      None,               "error",       1),
    ("SessionEnd",       None,               "off",         999),
]


def build_hook_group(event: str, matcher: str | None, status: str, priority: int) -> dict:
    """生成单个 traffic-light hook group。

    返回值形如:
        {"hooks": [{"type": "command", "async": True, "command": "..."}], "matcher": "..."}

    注意 matcher 只在 Notification 事件中出现。
    """
    python_path = str(VENV_PYTHON)
    hook_path = str(HOOK_SCRIPT)

    group: dict = {
        "hooks": [
            {
                "type": "command",
                "async": True,
                "command": f"{python_path} {hook_path} {event} {status} {priority}",
            }
        ]
    }
    if matcher:
        group["matcher"] = matcher

    return group


def is_traffic_light_group(group: dict) -> bool:
    """判断一个 hook group 是否属于 traffic-light。"""
    for hook in group.get("hooks", []):
        if "traffic-light-hook" in hook.get("command", ""):
            return True
    return False


def merge_settings(settings: dict) -> dict:
    """将 traffic-light hook 安全合并到 settings 中。

    合并策略：
      对每个 traffic-light 管理的事件：
        1. 确保该事件的数组存在
        2. 删除数组中所有包含 traffic-light-hook 的 group（旧路径）
        3. 追加新的 traffic-light group
      对不管理的事件：完全不动
      对 hooks 以外的字段（env、permissions 等）：完全不动
    """
    if "hooks" not in settings:
        settings["hooks"] = {}

    for event, matcher, status, priority in HOOK_DEFS:
        existing_groups = settings["hooks"].get(event, [])

        # 过滤掉所有旧的 traffic-light group，保留其他 group
        kept_groups = [g for g in existing_groups if not is_traffic_light_group(g)]

        # 追加新的 traffic-light group
        new_group = build_hook_group(event, matcher, status, priority)
        kept_groups.append(new_group)

        settings["hooks"][event] = kept_groups

    return settings


def read_settings() -> dict:
    """读取 settings.json，不存在则返回空 dict。"""
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_settings(settings: dict):
    """原子写入 settings.json。"""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = SETTINGS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(SETTINGS_FILE)


def main():
    print("🔧 交通灯 hook 安装")
    print(f"   项目目录: {PROJECT_DIR}")
    print(f"   Python:   {VENV_PYTHON}")
    print(f"   Hook脚本: {HOOK_SCRIPT}")
    print()

    existing = read_settings()

    # 统计现状
    existing_hook_events = set(existing.get("hooks", {}).keys())
    if existing_hook_events:
        print(f"   现有 settings.json 中有 {len(existing_hook_events)} 个 hook 事件: {', '.join(sorted(existing_hook_events))}")

    merged = merge_settings(existing)

    if DRY_RUN:
        print("\n--- 将要写入的 hooks 配置 (dry-run) ---")
        print(json.dumps(merged.get("hooks", {}), indent=2, ensure_ascii=False))
        return

    write_settings(merged)
    print("✅ hooks 配置已写入 ~/.claude/settings.json")
    print("   - 每个 traffic-light hook 在独立的 group 中，不干扰其他 hook")
    print("   - 已有配置保持原样")


if __name__ == "__main__":
    main()
