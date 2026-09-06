# -*- coding: utf-8 -*-
"""运行时目录解析：把「开发源码」与「本地运行数据」分离。

本地运行产生的数据（config.json / 日志 / 聊天记录 / 图片）统一写到运行时目录，
默认放在 git 仓库之外（Windows 为 E:\\rk3588\\ai-chat-runtime，Linux 为 ~/.ai-chat-runtime），
可用环境变量 AI_CHAT_RUNTIME 覆盖。这样 GitHub 上只管理公共源码，本地数据不入库。
"""

import os
import sys


def runtime_dir():
    """返回运行时目录（不存在则创建）。"""
    d = os.environ.get("AI_CHAT_RUNTIME")
    if not d:
        if sys.platform == "win32":
            d = r"E:\rk3588\ai-chat-runtime"
        else:
            d = os.path.expanduser("~/.ai-chat-runtime")
    os.makedirs(d, exist_ok=True)
    return d


def config_path():
    """返回 config.json（含密钥）的路径，位于运行时目录内。"""
    return os.path.join(runtime_dir(), "config.json")
