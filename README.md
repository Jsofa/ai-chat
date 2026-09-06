# ai-chat —— AI 聊天项目

命令行对话 + DeepSeek 网页服务 + 手机→Claude Code 桥，纯 Python 标准库，**零依赖、无需 pip 安装**。

三个入口：

| 文件 | 用途 | 运行位置 |
|------|------|----------|
| `chat.py` | 命令行多轮/单次对话 | 任意 |
| `server.py` | DeepSeek 网页服务（8000 端口） | VM / Linux |
| `claude_bridge.py` | 手机 → Claude Code 桥（8787 端口，SSE 流式） | Windows 本机 |

## 快速开始

```bash
cd ai-chat
cp config.example.json config.json
# 编辑 config.json，填入 api_key（见下）
python3 chat.py
```

## API 配置方法

`config.json` 是唯一的配置文件（**含密钥，已被 .gitignore 忽略，不入库**）：

```json
{
  "provider": "deepseek",
  "base_url": "",
  "model": "",
  "api_key": "sk-你的key",
  "bridge_token": "桥访问口令（claude_bridge 用）",
  "temperature": 0.7,
  "max_tokens": 2048,
  "stream": true
}
```

- **`provider`**：填下面任一个即可，`base_url`/`model` 留空会自动用预设：

  | provider  | 服务商   | 默认模型        |
  |-----------|----------|-----------------|
  | deepseek  | DeepSeek | deepseek-chat   |
  | qwen      | 通义千问 | qwen-plus       |
  | moonshot  | Moonshot | moonshot-v1-8k  |

- **`api_key`**：服务商密钥。`chat.py` / `server.py` 用。
- **`bridge_token`**：桥的访问口令（手机访问、log_viewer、notify_hook 共用）。`claude_bridge.py` / `log_viewer.py` / `notify_hook.py` 都从它读取，读不到再回退环境变量 `BRIDGE_TOKEN`。

也支持环境变量覆盖（优先级最高）：

```bash
export AI_API_KEY=你的key
export AI_BASE_URL=https://api.deepseek.com/chat/completions   # 可选
export AI_MODEL=deepseek-chat                                  # 可选
python3 chat.py
```

## 命令行用法

```bash
python3 chat.py            # 交互式多轮对话
python3 chat.py "你好"      # 单次提问，输出后退出
python3 chat.py --help
```

交互模式命令：`/exit` 退出、`/clear` 清空上下文、`/help` 帮助。

## 网页服务（DeepSeek）

在 VM 上运行，局域网/手机访问：

```bash
python3 server.py          # 监听 0.0.0.0:8000
# 浏览器打开 http://192.168.1.5:8000
```

## Claude Code 桥（手机找「我」）

在 Windows 本机运行：

```bash
pythonw.exe claude_bridge.py     # 后台跑，日志写 bridge.log
python claude_bridge.py          # 前台跑（调试用）
```

- 手机/局域网访问：`http://<本机IP>:8787`（本机 LAN IP 默认 192.168.1.2，DHCP 可能变）
- 监控页：`http://127.0.0.1:8787/log`
- **只能起一个实例**：Windows 的 SO_REUSEADDR 会让多实例同时监听 8787 导致连接串线，多实例先全停再起一个。
- 公网防护已内置：口令错 5 次封 IP 10 分钟、每 IP 120 次/分钟限流、并发 claude 进程上限 2。

重启：

```bash
netstat -ano | grep 8787 | grep -i listen   # 拿 PID
taskkill //F //PID <pid>
pythonw.exe claude_bridge.py
```

## 樱花内网穿透（Sakura Frp）

把桥暴露到公网，手机在外网也能连：

1. 注册 [Sakura Frp](https://www.natfrp.com/)，创建隧道：
   - 类型选 **HTTP / HTTPS**，本地 IP `127.0.0.1`、本地端口 **8787**。
2. 海外节点强制 HTTPS：隧道里开 **「自动 HTTPS」**，并**关闭「访问认证」**（桥已有 TOKEN，别开双层，否则 HTTP 501、HTTPS 握手失败）。
3. 启动 frpc（Windows 服务：`C:\ProgramData\SakuraFrpService\`），拿到公网地址（形如 `https://frp-sea.com:34605`）。
4. 手机打开公网地址 —— 自签证书，首次访问点「高级 → 继续前往」。

> 旧花生壳方案 `http://myopenaicode.top` 会断开，已弃用。

## 安全说明

- `config.json`（api_key + bridge_token）**已被 .gitignore 忽略，不会提交**。
- 源码里**不含任何明文密钥**，全部从 `config.json` 读取。
- 提交前请用 `git grep -n "sk-\|bridge_token 值" HEAD` 自查。
