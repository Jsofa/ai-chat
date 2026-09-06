#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 命令行对话工具（OpenAI 兼容 API：DeepSeek / 通义千问 / Moonshot 等）。

仅用 Python 标准库，无需 pip 安装任何包。支持多轮对话 + 流式输出。

配置（任选其一）：
  1. 复制 config.example.json 为 config.json，填入 api_key；
  2. 或用环境变量：AI_API_KEY / AI_BASE_URL / AI_MODEL。

用法：
  python3 chat.py            # 交互式多轮对话
  python3 chat.py "你好"      # 单次提问（非交互）
  python3 chat.py --help
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

import runtime_paths

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = runtime_paths.config_path()

# 常用服务商预设（均为 OpenAI 兼容的 /chat/completions 接口）
PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/chat/completions",
        "model": "deepseek-chat",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        "model": "qwen-plus",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1/chat/completions",
        "model": "moonshot-v1-8k",
    },
}

DEFAULT_CONFIG = {
    "provider": "deepseek",  # deepseek / qwen / moonshot
    "base_url": "",          # 留空则用 provider 预设；也可直接填完整 URL 覆盖
    "model": "",             # 留空则用 provider 默认模型
    "api_key": "",
    "temperature": 0.7,
    "max_tokens": 2048,
    "stream": True,
}

HELP_TEXT = """命令：
  /exit, /quit   退出
  /clear         清空当前对话上下文
  /help          显示本帮助
  直接输入文字    发送给 AI
"""


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except (OSError, json.JSONDecodeError) as e:
            print(f"警告：读取 {CONFIG_PATH} 失败（{e}），使用默认配置")

    # 环境变量覆盖
    if os.environ.get("AI_API_KEY"):
        cfg["api_key"] = os.environ["AI_API_KEY"]
    if os.environ.get("AI_BASE_URL"):
        cfg["base_url"] = os.environ["AI_BASE_URL"]
    if os.environ.get("AI_MODEL"):
        cfg["model"] = os.environ["AI_MODEL"]

    # 用 provider 预设补全 base_url / model
    provider = cfg.get("provider", "").lower()
    preset = PROVIDERS.get(provider)
    if preset:
        if not cfg.get("base_url"):
            cfg["base_url"] = preset["base_url"]
        if not cfg.get("model"):
            cfg["model"] = preset["model"]

    return cfg


def request_chat(cfg, messages):
    """发送一次请求，流式返回增量文本。"""
    body = {
        "model": cfg["model"],
        "messages": messages,
        "stream": cfg["stream"],
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
    }
    req = urllib.request.Request(
        cfg["base_url"],
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + cfg["api_key"],
        },
        method="POST",
    )

    # 非流式：一次返回完整内容
    if not cfg["stream"]:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        yield data["choices"][0]["message"]["content"]
        return

    # 流式：逐行解析 SSE（data: {...} / data: [DONE]）
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content")
            if piece:
                yield piece


def run_once(cfg, question):
    messages = [{"role": "user", "content": question}]
    try:
        for piece in request_chat(cfg, messages):
            sys.stdout.write(piece)
            sys.stdout.flush()
        print()
    except urllib.error.HTTPError as e:
        print(f"[HTTP {e.code}] {e.read().decode('utf-8', 'ignore')[:500]}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[网络错误] {e.reason}")
        sys.exit(1)
    except Exception as e:
        print(f"[错误] {e}")
        sys.exit(1)


def run_interactive(cfg):
    messages = []
    print(f"已连接：{cfg['base_url']}   模型：{cfg['model']}")
    print("输入 /help 查看命令，/exit 退出\n")
    while True:
        try:
            line = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见")
            break
        if not line:
            continue
        if line in ("/exit", "/quit"):
            print("再见")
            break
        if line == "/clear":
            messages.clear()
            print("已清空上下文")
            continue
        if line == "/help":
            print(HELP_TEXT, end="")
            continue

        messages.append({"role": "user", "content": line})
        sys.stdout.write("AI> ")
        sys.stdout.flush()
        answer = []
        try:
            for piece in request_chat(cfg, messages):
                answer.append(piece)
                sys.stdout.write(piece)
                sys.stdout.flush()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:500]
            print(f"\n[HTTP {e.code}] {detail}")
            messages.pop()
            continue
        except urllib.error.URLError as e:
            print(f"\n[网络错误] {e.reason}")
            messages.pop()
            continue
        except Exception as e:
            print(f"\n[错误] {e}")
            messages.pop()
            continue
        print()
        messages.append({"role": "assistant", "content": "".join(answer)})


def main():
    parser = argparse.ArgumentParser(description="AI 命令行对话工具")
    parser.add_argument("question", nargs="?", help="单次提问内容；不传则进入交互模式")
    args = parser.parse_args()

    cfg = load_config()
    if not cfg["api_key"]:
        print("未配置 api_key。请二选一：")
        print(f"  1) 在 {CONFIG_PATH} 里填 api_key")
        print("  2) 设置环境变量：export AI_API_KEY=你的key")
        sys.exit(1)

    if args.question:
        run_once(cfg, args.question)
    else:
        run_interactive(cfg)


if __name__ == "__main__":
    main()
