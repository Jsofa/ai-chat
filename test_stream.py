# -*- coding: utf-8 -*-
"""测试流式中文 + 多轮上下文。"""
import json
import urllib.request


def chat(msg):
    body = json.dumps({"message": msg}).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:8787/chat", data=body,
                                 headers={"Content-Type": "application/json",
                                          "X-Auth-Token": "8888"})
    resp = urllib.request.urlopen(req, timeout=120)
    acc = ""
    for raw in resp:
        line = raw.decode("utf-8").strip()
        if line.startswith("data:"):
            try:
                o = json.loads(line[5:].strip())
                if o.get("text"):
                    acc += o["text"]
            except Exception:
                pass
    return acc


r1 = chat("我的猫叫小白，请用一句话确认")
print("第1条回复:", r1)
r2 = chat("我的猫叫什么名字？一句话回答")
print("第2条回复:", r2)
