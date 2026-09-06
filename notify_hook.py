#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code hook：把 stdin 的 hook JSON 原样 POST 到桥的 /notify 接口。

被 settings.json 里的 PermissionRequest / Notification hook 调用。
不做任何 stdout 输出（hook 的 stdout 必须为空，避免污染控制流）。
"""
import json
import os
import sys
import urllib.request

import runtime_paths


def _load_token():
    """从 config.json 读桥口令，读不到回退环境变量 BRIDGE_TOKEN。"""
    _cfg_path = runtime_paths.config_path()
    try:
        with open(_cfg_path, "r", encoding="utf-8") as f:
            _cfg = json.load(f)
        if _cfg.get("bridge_token"):
            return _cfg["bridge_token"]
    except (OSError, ValueError):
        pass
    return os.environ.get("BRIDGE_TOKEN", "")

TOKEN = _load_token()
URL = "http://127.0.0.1:8787/notify"


def main():
    try:
        data = sys.stdin.buffer.read()
        req = urllib.request.Request(
            URL, data=data,
            headers={"Content-Type": "application/json", "X-Auth-Token": TOKEN})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass  # 通知失败不影响 hook 主流程


if __name__ == "__main__":
    main()
