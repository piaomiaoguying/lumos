# 物理红绿灯 × Claude Code Hook

USB 串口报警灯通过 Claude Code hook 实时呈现运行状态，无需看屏幕即可感知是否需要操作。

## 硬件

虹明机电 CH34x USB 串口报警灯（红黄蓝绿四色，`/dev/tty.usbserial-*`，9600 baud）。

## 灯 → 含义

| 灯 | 含义 | Claude Code 在做什么 | 触发条件 |
|----|------|---------------------|----------|
| 🟢 绿灯慢闪（亮1s 灭0.5s） | **working** | 正在执行工具 / 刚收到你的输入 | `UserPromptSubmit`、`PreToolUse`（用户批准权限后开始执行） |
| 🔵 蓝灯常亮 | **standby** | 输出完了 / 空闲等待，不用管 | `Stop`、`PermissionDenied`（仅自动模式）、`SessionStart`（无其他实例运行时） |
| 🟡 黄灯常亮 | **waiting_user** | MCP 服务器请求用户输入（如填表单），需要你回应 | `Elicitation`（仅 MCP 服务器触发；AskUserQuestion 走 PermissionRequest → 黄灯闪烁） |
| 🟡 黄灯慢闪（亮1s 灭0.5s） | **need_user** | 弹出确认框等你批准，或 Claude 提问多选题等你选择 | `PermissionRequest`（权限弹窗 / AskUserQuestion） |
| 🔴 红灯慢闪（亮1s 灭0.5s） | **error** | API 报错（限流/认证失败等） | `StopFailure` |
| ⚫ 全灭 | **off** | 无活跃会话 | `SessionEnd`（最后一个实例退出） |

> **注意**：`SessionStart` 切蓝灯有条件——仅在没有其他实例正在运行（灯是灭的）时才亮蓝灯。如果已有会话在工作（绿灯闪烁）或等待用户（黄灯闪烁），新会话不会抢灯。
> **注意**：`PermissionDenied` 仅在自动模式分类器拒绝工具时触发，灯切为蓝灯（standby），Claude 随后会解释原因或调整策略。手动在权限对话框中点 No 不会触发任何 hook 事件。
> **注意**：`Elicitation` 仅 MCP 服务器在工具执行中请求用户输入时触发。`AskUserQuestion` 工具（Claude 主动提问多选题）走 `PermissionRequest` 通道，表现为黄灯闪烁（`need_user`）。

## 状态转换

```text
SessionStart（无其他实例）→ 🔵 standby (蓝灯常亮)
SessionStart（有其他实例）→ 保持当前灯色，不抢灯

UserPromptSubmit ──────────→ 🟢 working (绿灯闪烁)
       │
       ├── PreToolUse ──────→ 🟢 working (绿灯闪烁，用户批准后继续执行)
       │
       ├── PermissionRequest
       │   └──────────────────→ 🟡 need_user (黄灯闪烁，权限弹窗 / Claude 提问等待回应)
       │       │
       │       ├── 用户点 Yes / 回答 → PreToolUse → 🟢 working
       │       └── 用户点 No  → (无 hook 事件，灯保持 need_user 直到实例退出或被新事件覆盖)
       │
       ├── Stop / PermissionDenied（仅自动模式）
       │   └──────────────────→ 🔵 standby (蓝灯常亮)
       ├── Elicitation（仅 MCP 服务器） → 🟡 waiting_user (黄灯常亮，MCP 请求用户输入）
       ├── StopFailure ─────→ 🔴 error (红灯闪烁)
       └── SessionEnd（且无其他实例）→ ⚫ off (全灭)
```

## 文件

```
.
├── traffic_light_controller.py   # 串口控制库（线程安全）
├── traffic_light_hook.py         # Hook 入口 + 多实例聚合引擎
├── traffic_light_blinker.py      # 软件呼吸灯（慢闪烁）
├── install.sh                    # 一键安装
├── install.py                    # Hook 配置合并
├── toggle_traffic_light.sh       # Hook / 日志 开关脚本
├── test_all.sh                   # 手动测试脚本
├── light_menu.sh                 # 灯光菜单
├── 虹明机电USB串口报警灯通讯说明.pdf
└── .venv/                        # 项目虚拟环境（安装后生成）
```

## 安装

```bash
./install.sh
```

脚本自动完成：创建虚拟环境 → 安装 pyserial → 创建符号链接 → 合并 hook 到 `~/.claude/settings.json` → 创建运行时目录。

> **如何合并 hook？** `install.py` 只管理 `traffic-light` 相关 hook，完全不动你已有的其他 hook 或配置。下次启动新的 Claude Code 会话时生效。

如需预览将要写入的 hook 配置：

```bash
.venv/bin/python install.py --dry-run
```

## 手动测试

```bash
# 依次测试所有灯色
.venv/bin/python traffic_light_controller.py --test-all

# 手动控制
.venv/bin/python traffic_light_controller.py --color green --mode on
.venv/bin/python traffic_light_controller.py --color all --mode off
```

或使用 bash 脚本：

```bash
bash test_all.sh          # 依次测试
bash light_menu.sh        # 交互菜单
```

## 开关

插拔设备时无需手动改配置——`SessionStart` 自动检测串口设备并刷新哨兵文件，后续 hook 读哨兵文件即可快速退出。

```bash
./toggle_traffic_light.sh            # 自动检测设备（默认）
./toggle_traffic_light.sh on         # 强制启用
./toggle_traffic_light.sh off        # 强制禁用
./toggle_traffic_light.sh status     # 查看状态（同时显示日志开关）
```

## 日志

Hook 每次触发都会记录决策日志到 `~/.claude/state/traffic-light/hook.log`，格式：

```
2026-06-04 11:29:04 5542b39a UserPromptSubmit working standby→working:green_blink
2026-06-04 11:29:04 5542b39a Stop working working→standby:blue_on
2026-06-04 11:29:09 5542b39a PermissionRequest need_user standby→need_user:yellow_blink
```

字段：`时间` | `session_id[:8]` | `事件` | `传入状态` | `决策结果`

日志**默认开启**，空间紧张时可禁用：

```bash
./toggle_traffic_light.sh log-on      # 启用日志
./toggle_traffic_light.sh log-off     # 禁用日志
./toggle_traffic_light.sh log-status  # 查看日志状态 + 最近 5 条
```

日志超过 100KB 自动截断到最后 500 行，不会无限增长。

## 架构

纯 hook 驱动，无常驻后台进程。

```
Claude Code Hook (async)
    ↓
traffic_light_hook.py <event> <status> <priority>
    │
    ├─ SessionStart → 自动检测设备，刷新哨兵文件
    ├─ 哨兵文件存在 → 快速退出（不加载控制器）
    ├─ 日志哨兵存在 → 跳过日志写入
    ├─ flock 全局锁 → 防多实例串口冲突
    ├─ 扫描 ~/.claude/state/traffic-light/instances/ → 多实例聚合
    ├─ 聚合实例状态（后触发者胜，闪烁状态有锁保护，新会话不抢灯）
    ├─ SessionStart 有其他灯运行时抑制蓝灯，仅该灭时切蓝灯
    ├─ 状态切换时先全关再设新状态，避免颜色残留
    ├─ 常亮/灭 → 直接串口命令
    └─ 闪烁   → 启动软件呼吸灯进程（亮1s灭0.5s）
```

多实例时**后触发者胜**——非闪烁状态下谁最后更新就听谁的。闪烁状态（need_user、error）一旦确立，只有同一实例自己变、更高优先级闪烁升级、或该实例退出（SessionEnd）才能覆盖，不会被其他实例的低优先级信号抢走。SessionEnd 只删除本实例的状态文件，如果还有其他实例存活，灯会切换为该实例的状态而非全灭。
