# ai-chat —— AI 聊天项目

命令行对话 + DeepSeek 网页服务 + 手机→Claude Code 桥。**纯 Python 标准库，零依赖**（仅 `log_viewer.py` 需 PyQt5）。

## 目录结构

```
ai-chat/                     ← 源码目录（GitHub 管理，只放公共代码）
├── chat.py                  命令行对话（多轮/单次）
├── server.py                DeepSeek 网页服务（端口 8000）
├── claude_bridge.py         手机→Claude Code 桥（端口 8787，SSE 流式）
├── runtime_paths.py         运行时目录解析
├── log_viewer.py            桌面聊天监控窗口（需 PyQt5）
├── notify_hook.py           Claude Code hook（通知桥）
├── serve_image.py           图片服务
├── extract_pdf.py           PDF 抽取工具
├── guide.html / emei.html   桥的静态页
├── config.example.json      配置模板（空密钥，照填即可）
├── test_*.py                测试脚本
└── README.md

~/.ai-chat-runtime/          ← 运行时目录（本地，不入库；可被 AI_CHAT_RUNTIME 覆盖）
├── config.json              你的真实配置（含密钥，这里填）
├── bridge.log               桥日志
├── chat_log.jsonl / .xlsx   聊天记录
└── images/                  聊天图片
```

## 环境要求

- **Python 3.8+**（项目只用标准库，**无需 pip install 任何包**）
- 可选：`log_viewer.py`（桌面监控）需 `pip install PyQt5`
- 桥依赖本机装有 [Claude Code](https://claude.ai/code) 的 `claude` CLI

## 快速开始（克隆 → 配置 → 运行）

```bash
git clone https://github.com/<你的账号>/ai-chat.git
cd ai-chat

# 1. 生成配置（复制模板到运行时目录）
cp config.example.json ~/.ai-chat-runtime/config.json   # Windows 用 C:\Users\<你>\.ai-chat-runtime\config.json

# 2. 编辑 config.json，填入 api_key（见下方「配置说明」）

# 3. 运行
python chat.py                 # 命令行对话
# 或 python server.py          # 网页服务（8000）
# 或 python claude_bridge.py   # Claude Code 桥（8787）
```

## 配置说明（`~/.ai-chat-runtime/config.json`）

```json
{
  "provider": "deepseek",     // 服务商：deepseek / qwen / moonshot
  "base_url": "",             // 留空用预设；也可填完整接口 URL 覆盖
  "model": "",                // 留空用 provider 默认模型
  "api_key": "sk-你的key",     // 【必填】服务商密钥
  "bridge_token": "自定义口令", // 【桥必填】手机访问桥的口令（chat/server 用不到）
  "temperature": 0.7,
  "max_tokens": 2048,
  "stream": true
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `provider` | 是 | 服务商，预设见下表 |
| `api_key` | 是 | API 密钥（DeepSeek 等平台申请） |
| `bridge_token` | 仅桥 | 手机访问桥的访问口令，随意设个强随机字符串 |
| `base_url` / `model` | 否 | 留空自动用预设 |
| `temperature` / `max_tokens` / `stream` | 否 | 生成参数 |

服务商预设：

| provider  | 服务商   | 默认模型        |
|-----------|----------|-----------------|
| deepseek  | DeepSeek | deepseek-chat   |
| qwen      | 通义千问 | qwen-plus       |
| moonshot  | Moonshot | moonshot-v1-8k  |

也支持环境变量覆盖（优先级最高）：`AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL` / `AI_CHAT_RUNTIME`（自定义运行时目录）/ `BRIDGE_TOKEN`。

## 端口说明

| 端口 | 组件 | 用途 |
|------|------|------|
| 8000 | `server.py` | DeepSeek 网页服务 |
| 8787 | `claude_bridge.py` | 手机→Claude Code 桥 |

## 本地 IP 说明（手机访问用）

桥/网页服务都监听 `0.0.0.0`，手机用**电脑的局域网 IP** 访问：

- 查本机 IP：Windows 里 `ipconfig` 看 IPv4（例如 `192.168.1.2`），Linux 里 `ip addr`。
- 手机与电脑连**同一 WiFi**，浏览器打开 `http://<本机IP>:8787`（桥）或 `http://<本机IP>:8000`（网页）。
- 注意：DHCP 分配的 IP **可能变**，连不上先重新 `ipconfig` 确认。

## 各组件用法

```bash
python chat.py              # 交互式多轮对话
python chat.py "你好"        # 单次提问
python chat.py --help
# 交互命令：/exit 退出、/clear 清空、/help 帮助

python server.py            # 网页服务，浏览器 http://<本机IP>:8000

python claude_bridge.py     # 桥（前台，调试用）
pythonw claude_bridge.py    # 桥（Windows 后台，日志写运行时目录 bridge.log）
```

## 桥的模型依赖（Claude Code + cc-switch）

桥本身只调 `claude -p`（Claude Code CLI），模型从哪来由 Claude Code 的配置决定。本机当前链路：

    手机 → claude_bridge.py(8787) → claude -p(Claude Code) → cc-switch 本地代理(127.0.0.1:15721) → DeepSeek

- **Claude Code**：干活主体（跑工具、执行命令、多轮对话）。
- **cc-switch**（CC Switch）：供应商切换器 + 本地翻译代理，把 Claude Code 的 Anthropic 格式请求翻成 OpenAI 格式发给 DeepSeek，并做模型名映射（haiku→deepseek-v4-flash、sonnet/opus→deepseek-v4-pro）。

**为什么有 cc-switch**：Claude Code 默认连 Anthropic 官方 API（付费、国内直连难）；本机想用 DeepSeek（便宜、国内可通），两者接口格式不同需要翻译代理，cc-switch 就是这层代理 + 切换器。它不是硬依赖，可替换：

| 方案 | 说明 |
|------|------|
| 官方 Claude | 去掉 `~/.claude/settings.json` 里的 `ANTHROPIC_BASE_URL` 等，登录 Anthropic 账号即可，无需 cc-switch（需订阅） |
| 其它代理 | 用 `claude-code-router` / `one-api` / `new-api` 等替代 cc-switch 的代理角色 |
| Anthropic 兼容网关 | 直接把 `ANTHROPIC_BASE_URL` 指向支持 Anthropic 接口的服务商 |

> 运行桥需要 cc-switch 的本地代理（15721）在线；桥靠 `start_bridge.vbs` 自启、cc-switch 也开机自启，两者都在则整条链就绪。

## 樱花内网穿透（Sakura Frp，手机外网访问）

1. 注册 [Sakura Frp](https://www.natfrp.com/)，创建隧道：类型 **HTTP/HTTPS**，本地 `127.0.0.1:8787`。
2. 海外节点强制 HTTPS：开 **「自动 HTTPS」**、关 **「访问认证」**（桥已有 bridge_token，别开双层）。
3. 启动 frpc 拿到公网地址（形如 `https://你的节点.frp.com:端口`）。
4. 手机打开该地址，自签证书首次点「高级 → 继续前往」。

## 安全说明

- **`config.json`（含 api_key / bridge_token）放在运行时目录，不进源码目录、不上传 GitHub。**
- 源码里**不含任何明文密钥**，全部从运行时目录的 config.json 读取。
- 提交前自查：`git grep -n "sk-" HEAD`。
