#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Claude Code 聊天记录实时监控窗口（PyQt5 桌面版）。

每 2 秒轮询桥的 /history 接口，实时显示手机与 Claude Code 的对话。
用 QTextBrowser + HTML 渲染，窗口可自由拉伸，用户/AI 消息清晰区分。
运行：python log_viewer.py
"""

import html
import json
import os
import sys
import urllib.request

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QLabel, QPushButton,
                             QTextBrowser, QVBoxLayout, QWidget)

def _load_token():
    """从 config.json 读桥口令，读不到回退环境变量 BRIDGE_TOKEN。"""
    _cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    try:
        with open(_cfg_path, "r", encoding="utf-8") as f:
            _cfg = json.load(f)
        if _cfg.get("bridge_token"):
            return _cfg["bridge_token"]
    except (OSError, ValueError):
        pass
    return os.environ.get("BRIDGE_TOKEN", "")

BASE = "http://127.0.0.1:8787"
TOKEN = _load_token()
XLSX = r"E:\rk3588\code\ai-chat\chat_log.xlsx"


def fetch_history():
    try:
        req = urllib.request.Request(BASE + "/history?token=" + TOKEN)
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return []


class Viewer(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Claude Code 聊天记录监控")
        self.resize(520, 760)
        self._last_count = -1

        root = QVBoxLayout(self)
        head = QHBoxLayout()
        title = QLabel("Claude Code 聊天记录")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        open_btn = QPushButton("打开 Excel")
        open_btn.clicked.connect(self.open_xlsx)
        head.addWidget(title)
        head.addStretch()
        head.addWidget(open_btn)
        root.addLayout(head)

        self.browser = QTextBrowser()
        root.addWidget(self.browser)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()

    def open_xlsx(self):
        if os.path.exists(XLSX):
            os.startfile(XLSX)
        else:
            print("chat_log.xlsx 不存在")

    def refresh(self):
        items = fetch_history()
        if len(items) == self._last_count:
            return
        self._last_count = len(items)
        parts = []
        for e in items:
            role = e["role"]
            text = html.escape(str(e["text"]))
            ts = html.escape(str(e["time"]))
            img = e.get("image")
            if role == "用户":
                img_html = ""
                if img and os.path.exists(img):
                    img_html = f'<div style="margin-top:4px"><img src="file:///{img}" style="max-width:260px;border-radius:8px"></div>'
                parts.append(
                    '<div style="margin:6px 0;text-align:right">'
                    f'<div style="color:#999;font-size:11px">{ts} · 用户</div>'
                    f'<div style="display:inline-block;background:#d3e6ff;border-radius:8px;padding:8px 12px;max-width:75%;text-align:left;white-space:pre-wrap">{text}</div>'
                    f'{img_html}'
                    '</div>')
            else:
                parts.append(
                    '<div style="margin:6px 0">'
                    f'<div style="color:#999;font-size:11px">{ts} · AI</div>'
                    f'<div style="display:inline-block;background:#ffffff;border-radius:8px;padding:8px 12px;max-width:75%;text-align:left;white-space:pre-wrap">{text}</div>'
                    '</div>')
        self.browser.setHtml(
            '<body style="font-family:Microsoft YaHei;font-size:14px;margin:8px">'
            + ''.join(parts) + '</body>')
        QTimer.singleShot(60, lambda: self.browser.verticalScrollBar().setValue(
            self.browser.verticalScrollBar().maximum()))


def main():
    app = QApplication(sys.argv)
    v = Viewer()
    v.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
