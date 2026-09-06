# -*- coding: utf-8 -*-
"""claude_bridge 的本地测试：用 UTF-8 发中文消息，验证端到端。"""
import json
import urllib.request

# 1. GET 首页
with urllib.request.urlopen("http://127.0.0.1:8787/", timeout=10) as r:
    html = r.read().decode("utf-8")
print(f"[1] GET / -> HTTP {r.status}, 页面 {len(html)} 字节")

# 2. POST 中文消息
body = json.dumps({"message": "只回复两个字：收到"}).encode("utf-8")
req = urllib.request.Request("http://127.0.0.1:8787/chat", data=body,
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=180) as r:
    data = json.loads(r.read().decode("utf-8"))
print(f"[2] POST /chat -> HTTP {r.status}")
print(f"    回复: {data.get('reply', '')}")
