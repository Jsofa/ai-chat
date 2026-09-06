# -*- coding: utf-8 -*-
"""测试 claude -p 用 stream-json 输入传图片。"""
import base64
import json
import subprocess

with open("images/test.jpg", "rb") as f:
    data = f.read()
print("图片大小:", len(data), "魔数:", data[:4])

b64 = base64.b64encode(data).decode()
msg = {
    "type": "user",
    "message": {
        "role": "user",
        "content": [
            {"type": "text", "text": "Describe this image in one short sentence."},
            {"type": "image",
             "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
        ],
    },
}
payload = json.dumps(msg) + "\n"

cmd = ["claude", "-p", "--input-format", "stream-json",
       "--output-format", "stream-json", "--verbose",
       "--dangerously-skip-permissions"]
proc = subprocess.run(cmd, input=payload, capture_output=True, text=True,
                      encoding="utf-8", errors="replace", timeout=120,
                      cwd=r"E:\rk3588\code")
print("--- 解析输出 ---")
for line in proc.stdout.splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        evt = json.loads(line)
    except Exception:
        continue
    if evt.get("type") == "result":
        print("RESULT:", evt.get("result"))
        print("IS_ERROR:", evt.get("is_error"))
        print("SESSION:", evt.get("session_id"))
print("--- stderr ---")
print(proc.stderr[:400])
