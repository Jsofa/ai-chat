#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 AI 对话暴露成网页服务，手机等设备用浏览器即可与 AI 对话。

启动后，同一 WiFi 下的手机浏览器访问 http://<本机IP>:8000 即可。
仅用 Python 标准库，复用 chat.py 的配置与请求逻辑。
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import chat

HOST = "0.0.0.0"
PORT = 8000

HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>AI 对话</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f5f6f8; color: #222; }
  header { background: #fff; padding: 12px 16px; border-bottom: 1px solid #e5e5e5;
           display: flex; align-items: center; justify-content: space-between; }
  header h3 { margin: 0; font-size: 16px; }
  header button { border: 1px solid #ddd; background: #fff; border-radius: 6px;
                  padding: 4px 10px; font-size: 13px; }
  #chat { height: calc(100vh - 110px); overflow-y: auto; padding: 12px 16px; }
  .msg { margin: 8px 0; padding: 10px 12px; border-radius: 12px; line-height: 1.5;
         max-width: 82%; white-space: pre-wrap; word-break: break-word; font-size: 15px; }
  .user { background: #d3e6ff; margin-left: auto; border-bottom-right-radius: 4px; }
  .ai   { background: #fff; margin-right: auto; border-bottom-left-radius: 4px;
          box-shadow: 0 1px 2px rgba(0,0,0,.05); }
  #input { position: fixed; left: 0; right: 0; bottom: 0; background: #fff;
           padding: 10px 12px; display: flex; gap: 8px; border-top: 1px solid #e5e5e5; }
  #msg { flex: 1; border: 1px solid #ddd; border-radius: 20px; padding: 10px 14px;
         font-size: 15px; outline: none; }
  #send { border: 0; background: #2f6fed; color: #fff; border-radius: 20px;
          padding: 0 20px; font-size: 15px; }
</style>
</head>
<body>
<header>
  <h3>AI 对话</h3>
  <button id="clear">清空</button>
</header>
<div id="chat"></div>
<div id="input">
  <input id="msg" placeholder="输入消息…">
  <button id="send">发送</button>
</div>
<script>
const chatEl = document.getElementById('chat');
const msgEl = document.getElementById('msg');
let messages = [];

function add(role, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function send() {
  const text = msgEl.value.trim();
  if (!text) return;
  msgEl.value = '';
  add('user', text);
  messages.push({ role: 'user', content: text });
  const tip = document.createElement('div');
  tip.className = 'msg ai';
  tip.textContent = '思考中…';
  chatEl.appendChild(tip);
  chatEl.scrollTop = chatEl.scrollHeight;
  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages })
    });
    const data = await res.json();
    tip.remove();
    if (data.reply) {
      add('ai', data.reply);
      messages.push({ role: 'assistant', content: data.reply });
    } else {
      add('ai', '出错：' + (data.error || '未知错误'));
    }
  } catch (e) {
    tip.remove();
    add('ai', '网络错误：' + e);
  }
}

document.getElementById('send').onclick = send;
msgEl.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });
document.getElementById('clear').onclick = () => {
  messages = [];
  chatEl.innerHTML = '';
};
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/chat":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            messages = data.get("messages") or []
            if not messages:
                return self._json(400, {"error": "messages 不能为空"})
            cfg = chat.load_config()
            reply = "".join(chat.request_chat(cfg, messages))
            self._json(200, {"reply": reply})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    cfg = chat.load_config()
    print(f"AI 聊天服务已启动，模型：{cfg['model']}")
    print(f"本机访问：http://127.0.0.1:{PORT}")
    print(f"手机访问：http://<本机IP>:{PORT}   （需同一 WiFi/局域网）")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
