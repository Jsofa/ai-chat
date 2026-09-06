#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""server.py 冒烟测试：验证首页可访问、/chat 能返回 AI 回复。"""
import json
import urllib.request

BASE = "http://127.0.0.1:8000"

# 1. GET 首页
try:
    with urllib.request.urlopen(BASE + "/", timeout=10) as r:
        html = r.read().decode("utf-8")
    print(f"[1] GET / -> HTTP {r.status}, 页面大小 {len(html)} 字节")
except Exception as e:
    print(f"[1] GET / 失败: {e}")

# 2. POST /chat
body = json.dumps({"messages": [{"role": "user", "content": "用一句话介绍你自己"}]}).encode()
req = urllib.request.Request(BASE + "/chat", data=body,
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    reply = data.get("reply", "")
    print(f"[2] POST /chat -> HTTP {r.status}")
    print(f"    回复: {reply[:200]}")
except Exception as e:
    print(f"[2] POST /chat 失败: {e}")
