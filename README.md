## fwlog-ws-backend

一个用于「聊天记录转海豹原始日志」的后端脚本。

它通过 OneBot v11 WebSocket 接入 NapCat / LLOneBot，识别 QQ 的【合并转发】消息，将其中的聊天内容提取出来，并转换为跑团染色器（SealDice）可识别的原始日志文本格式，最终以 txt 文件的形式发送回 QQ。

### 功能简介

- 连接 NapCat / LLOneBot 的 OneBot v11 正向 WebSocket
- 识别群聊 / 私聊中的【合并转发】消息
- 将转发内容转换为 SealDice 原生日志格式
- 支持多 Bot 实例（多个 NapCat / LLOneBot）
- 日志数据持久化到 SQLite（`fwlog.db`），可跨重启保留
- 直接将日志以 txt 文件形式发送到 QQ（群聊 / 私聊均支持）
- 提供 Windows / Linux 一键启动脚本

### 目录结构

- `fwlog_ws_bot.py`：主脚本，负责连接 OneBot、处理指令和合并转发消息
- `requirements.txt`：Python 依赖列表
- `start_fwlog_win.bat`：Windows 一键启动脚本
- `start_fwlog_linux.sh`：Linux 一键启动脚本（后台使用 screen 运行）
- `fwlog使用说明.txt`：更详细的中文使用说明

### 环境要求

- Python 3.9+（建议）
- 已部署好的 NapCat 或 LLOneBot，启用 OneBot v11 WebSocket
- 能访问 NapCat / LLOneBot WebSocket 的运行环境（物理机 / 容器均可）

### 快速开始

1. 克隆仓库：

```bash
git clone https://github.com/chaye2333/fwlog-ws-backend.git
cd fwlog-ws-backend
```

2. 配置 Bot 连接信息：

用编辑器打开 `fwlog_ws_bot.py`，找到开头的 `BOT_CONFIGS` 区域，按实际情况填写：

```python
BOT_CONFIGS = [
    {
        "name": "bot1",
        "url": "ws://127.0.0.1:3001",
        "token": ""
    },
    # 可以按需继续添加其他 NapCat / LLOneBot 实例
]
```

3. 启动后端：

- 在 **Windows** 上：

  直接双击 `start_fwlog_win.bat`。  
  脚本会自动创建虚拟环境、安装依赖并启动后端。

- 在 **Linux** 上：

  ```bash
  chmod +x start_fwlog_linux.sh
  ./start_fwlog_linux.sh
  ```

  会在后台创建一个名为 `fwlog_bot` 的 screen 会话。

### 指令说明

在 QQ 群聊或私聊中，对接入的 Bot 发送以下指令（必须带前缀，如 `.` 或 `/`）：

- `.fwlog new [名称]`  
  新建并开始记录合并转发日志。如果未提供名称，会自动生成一个时间戳名称。

- `.fwlog on [名称]`  
  继续记录指定名称的已有日志。

- `.fwlog off`  
  暂停当前日志记录，但不清除内容。

- `.fwlog end [名称]`  
  结束指定日志，并将完整日志作为 txt 文件发送到当前会话。

- `.fwlog get [名称]`  
  获取指定日志当前内容，作为 txt 文件发送。

- `.fwlog list`  
  列出当前会话下的所有 fwlog 日志及状态。

- `.fwlog clear [名称]`  
  清除指定日志记录。

> 说明：本工具只处理【合并转发】消息，不会记录普通实时聊天。用于补全漏记的跑团日志，再导入到 SealDice / 跑团染色器中使用。

