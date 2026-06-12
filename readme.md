# 🪄 Lumos — 让 AI 有了实体感官

> **不用看屏幕，就知道 Claude Code 在干嘛。**
>
> 物理 USB 红绿灯实时映射 Claude Code 运行状态——AI 思考时绿灯闪烁、卡在权限等你说"yes"时黄灯闪烁、报错了红灯警报。把 AI 的数字灵魂装进一盏真实的灯里。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

---

## ✨ 为什么你需要 Lumos

Claude Code 在终端里跑着，你是不是经常这样：

- 🔄 切到别的窗口干别的事，不知道 AI 还在跑还是已经卡住了
- 😵 开着好几个 Terminal 窗口，不知道哪个在等你回复
- 🔕 后台跑任务，隔几分钟切回去看一眼——大多数时候啥也没发生

**Lumos 把 AI 的状态从屏幕里拽了出来。** 看一眼桌上的灯，你就知道一切。

## 🎬 怎么玩

插上灯，一行命令：

```bash
curl -sSL https://raw.githubusercontent.com/piaomiaoguying/lumos/master/install.sh | bash
```

然后正常用 Claude Code。灯会自己亮。

## 💡 灯语

| 灯 | 含义 | 你在干嘛 |
|----|------|---------|
| 🟢 绿灯慢闪 | **AI 在干活** | 切出去摸鱼，绿灯在闪就放心 |
| 🔵 蓝灯常亮 | **AI 空闲等你** | 它输出完了，该你看了 |
| 🟡 黄灯慢闪 | **需要你批准/回答** | 弹出确认框或多选题，快去点 |
| 🟡 黄灯常亮 | **MCP 工具等待输入** | 填表单之类，需要你回应 |
| 🔴 红灯慢闪 | **出错了** | API 限流/认证失败，快去救 |
| ⚫ 全灭 | **没有活跃会话** | 下班了，关灯走人 |

> 🧙 **哈利波特梗**：打开 Claude Code 的那一刻，你说出咒语 **"Lumos"**，荧光闪烁照亮了 AI 的灵魂。

## 🧬 不是 GIF，是真灯

这不是一个花哨的终端 UI 插件。它是一盏**真的 USB 串口报警灯**，摆在桌上、插在电脑上。你的 AI coding agent 有了物理存在感——像《攻壳机动队》里的幽灵在壳里有了躯壳。

## 🏗️ 架构

```
Claude Code Hook (async)
    ↓
traffic_light_hook.py  ← 纯 hook 驱动，无常驻进程
    │
    ├─ SessionStart → 自动检测设备
    ├─ 多实例聚合引擎 → 后触发者胜
    ├─ 闪烁锁 → need_user/error 不受低优先级干扰
    ├─ flock 全局锁 → 防串口冲突
    └─ USB 串口 → 物理灯
```

**0 CPU 占用，0 后台进程。** Hook 触发时才跑，跑完即退。多实例安全，不会抢串口。

## 📦 硬件

虹明机电 CH34x USB 串口报警灯（红黄蓝绿四色），淘宝 30 块钱。

## 🛠️ 命令

```bash
./install.sh                          # 一键安装
./toggle_traffic_light.sh             # 开关灯（插拔后自动检测）
./toggle_traffic_light.sh off         # 关灯摸鱼
.venv/bin/python traffic_light_controller.py --test-all  # 测试所有灯色
```

## 📜 许可

MIT

---

<p align="center">
  <i>Lumos — 让 AI 从终端里走出来。</i><br>
  <sub>不是科幻，是一盏灯。</sub>
</p>
