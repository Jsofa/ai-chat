# -*- coding: utf-8 -*-
"""极简图片服务：把 heart.png 通过网页发给手机。运行后手机访问 http://<本机IP>:8899/"""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8899
IMG = r"E:\rk3588\code\heart.png"

HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>爱心 ❤</title>
<style>
  body { margin: 0; min-height: 100vh; display: flex; flex-direction: column;
         align-items: center; justify-content: center; background: #1e1e2e;
         color: #fff; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; }
  img { max-width: 90vw; max-height: 78vh; border-radius: 16px;
        box-shadow: 0 12px 40px rgba(0,0,0,.5); }
  a { margin-top: 18px; display: inline-block; padding: 12px 28px; border-radius: 24px;
      background: #ff5c8a; color: #fff; text-decoration: none; font-size: 16px; }
  a:active { transform: scale(.96); }
</style>
</head>
<body>
  <img src="/heart.png" alt="爱心">
  <a href="/heart.png" download="heart.png">保存图片</a>
</body>
</html>"""


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/heart.png":
            with open(IMG, "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Disposition", "inline; filename=heart.png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
