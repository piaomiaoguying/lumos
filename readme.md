# 物理红绿灯 × Claude Code Hook

USB 串口报警灯通过 Claude Code hook 实时呈现运行状态，无需看屏幕即可感知是否需要操作。

## 硬件

虹明机电 CH34x USB 串口报警灯（红黄蓝绿四色，`/dev/tty.usbserial-*`，9600 baud）。

## 灯 → 含义

| 灯 | 含义 | Claude Code 在做什么 |
|----|------|---------------------|
| 🟢 绿灯慢闪（亮1.5s 灭0.5s） | **working** | 正在执行工具 / 刚收到你的输入 |
| 🟢 绿灯常亮 | **standby** | 输出完了，不用管 |
| 🟡 黄灯常亮 | **waiting_user** | 等你输入/回答问题 |
| 🟡 黄灯慢闪 | **need_user** | 弹出确认框，等你批准 |
| 🔴 红灯慢闪 | **error** | API 报错（限流/认证失败等） |
| ⚫ 全灭 | **off** | 无活跃会话 |

## 文件

```
.
├── traffic_light_controller.py   # 串口控制库（线程安全）
├── traffic_light_hook.py         # Hook 入口 + 多实例聚合引擎
├── traffic_light_blinker.py      # 软件呼吸灯（慢闪烁）
├── test_all.sh                   # 手动测试脚本
├── light_menu.sh                 # 灯光菜单
├── 虹明机电USB串口报警灯通讯说明.pdf
└── .venv/                        # 项目虚拟环境
```

## 安装

### 1. 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pyserial
```

### 2. 创建符号链接

```bash
mkdir -p ~/.claude/scripts
ln -sf "$(pwd)/traffic_light_hook.py" ~/.claude/scripts/traffic-light-hook
```

### 3. 配置 Claude Code hooks

在 `~/.claude/settings.json` 中添加：

```json
"hooks": {
  "SessionStart": [{"hooks": [{"type": "command", "command": ".venv/bin/python ~/.claude/scripts/traffic-light-hook SessionStart standby 5", "async": true}]}],
  "UserPromptSubmit": [{"hooks": [{"type": "command", "command": ".venv/bin/python ~/.claude/scripts/traffic-light-hook UserPromptSubmit working 4", "async": true}]}],
  "PreToolUse": [{"hooks": [{"type": "command", "command": ".venv/bin/python ~/.claude/scripts/traffic-light-hook PreToolUse working 4", "async": true}]}],
  "Stop": [{"hooks": [{"type": "command", "command": ".venv/bin/python ~/.claude/scripts/traffic-light-hook Stop standby 5", "async": true}]}],
  "PermissionRequest": [{"hooks": [{"type": "command", "command": ".venv/bin/python ~/.claude/scripts/traffic-light-hook PermissionRequest need_user 2", "async": true}]}],
  "Notification": [
    {"matcher": "permission_prompt", "hooks": [{"type": "command", "command": ".venv/bin/python ~/.claude/scripts/traffic-light-hook Notification need_user 2", "async": true}]},
    {"matcher": "idle_prompt", "hooks": [{"type": "command", "command": ".venv/bin/python ~/.claude/scripts/traffic-light-hook Notification waiting_user 3", "async": true}]}
  ],
  "Elicitation": [{"hooks": [{"type": "command", "command": ".venv/bin/python ~/.claude/scripts/traffic-light-hook Elicitation waiting_user 3", "async": true}]}],
  "StopFailure": [{"hooks": [{"type": "command", "command": ".venv/bin/python ~/.claude/scripts/traffic-light-hook StopFailure error 1", "async": true}]}],
  "SessionEnd": [{"hooks": [{"type": "command", "command": ".venv/bin/python ~/.claude/scripts/traffic-light-hook SessionEnd off 999", "async": true}]}]
}
```

## 手动测试

```bash
# 依次测试所有灯色
.venv/bin/python traffic_light_controller.py --test-all

# 手动控制
.venv/bin/python traffic_light_controller.py --color green --mode on
.venv/bin/python traffic_light_controller.py --all-off
```

或使用 bash 脚本：

```bash
bash test_all.sh          # 依次测试
bash light_menu.sh        # 交互菜单
```

## 架构

纯 hook 驱动，无常驻后台进程。

```
Claude Code Hook (async)
    ↓
traffic_light_hook.py <event> <status> <priority>
    │
    ├─ flock 全局锁 → 防多实例串口冲突
    ├─ 扫描 ~/.claude/state/traffic-light/instances/ → 多实例聚合
    ├─ 取最高优先级状态
    ├─ 常亮/灭 → 直接串口命令
    └─ 闪烁   → 启动软件呼吸灯进程（亮1.5s灭0.5s）
                    └─ 状态切换时被 SIGTERM 终止
```

多实例时取所有实例中优先级最高的状态驱动灯。
