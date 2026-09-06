#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手机 → Claude Code 桥服务（运行在本机 Windows，流式输出 + 聊天记录 + 图片）。

- 手机发文字/图片 → 调用本机 claude CLI（stream-json）→ SSE 流式返回。
- 每条对话写入 chat_log.xlsx（时间/角色/内容/图片路径）。
- 图片保存到 images/ 目录，聊天页与监控窗口可显示。
- /log 网页监控页；log_viewer.py 为 PyQt 桌面监控窗口。

带访问口令（TOKEN）。仅用 Python 标准库。
运行：python claude_bridge.py   手机访问：http://<本机IP>:8787
"""

import base64
import json
import os
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

import runtime_paths

try:
    _log_path = os.path.join(runtime_paths.runtime_dir(), "bridge.log")
    sys.stdout = open(_log_path, "a", encoding="utf-8", buffering=1)
    sys.stderr = sys.stdout
except OSError:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
    sys.stderr = sys.stdout

HOST = "0.0.0.0"
PORT = 8787
WORKDIR = r"E:\rk3588\code"
MODEL = "haiku"  # haiku→flash(deepseek-v4-flash)；空串/默认→pro(deepseek-v4-pro)
def _load_token():
    """从 config.json 读桥访问口令，读不到再回退环境变量 BRIDGE_TOKEN。"""
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

_HERE = os.path.dirname(os.path.abspath(__file__))
_RUNTIME = runtime_paths.runtime_dir()
IMAGES_DIR = os.path.join(_RUNTIME, "images")
XLSX_PATH = os.path.join(_RUNTIME, "chat_log.xlsx")
JSONL_PATH = os.path.join(_RUNTIME, "chat_log.jsonl")
GUIDE_PATH = os.path.join(_HERE, "guide.html")
EMEI_PATH = os.path.join(_HERE, "emei.html")
os.makedirs(IMAGES_DIR, exist_ok=True)

session_id = None
_lock = threading.Lock()
history = []
_current_proc = None  # 当前 claude 子进程，客户端断开时用于杀掉

# —— 公网防护：速率限制 + 口令错误封禁 + 并发上限 ——
MAX_CONCURRENT = 2      # 同时最多 2 个 claude 进程（防止刷爆配额）
BAN_THRESHOLD = 5       # 连续 5 次口令错误即封禁该 IP
BAN_SECONDS = 600       # 封禁时长 10 分钟
RATE_LIMIT = 120        # 每分钟最多 120 次请求
RATE_WINDOW = 60        # 速率统计窗口（秒）
_guard_lock = threading.Lock()
_proc_sem = threading.Semaphore(MAX_CONCURRENT)
_ban = {}               # ip -> 封禁到期时间戳
_fails = {}             # ip -> 连续口令失败次数
_reqs = {}              # ip -> [请求时间戳, ...]

HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Claude Code</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f5f6f8; color: #222; }
  header { background: #fff; padding: 12px 16px; border-bottom: 1px solid #e5e5e5;
           display: flex; align-items: center; justify-content: space-between; }
  header h3 { margin: 0; font-size: 16px; }
  header .badge { font-size: 11px; color: #2f6fed; background: #eaf1ff; border-radius: 10px;
                  padding: 2px 8px; margin-left: 8px; }
  header button { border: 1px solid #ddd; background: #fff; border-radius: 6px;
                  padding: 4px 10px; font-size: 13px; }
  #auth { display: flex; gap: 8px; padding: 8px 16px; background: #fff8e6;
          border-bottom: 1px solid #f0e0b0; align-items: center; }
  #auth input { flex: 1; border: 1px solid #ddd; border-radius: 6px; padding: 8px 12px;
                font-size: 14px; outline: none; }
  #auth button { border: 0; background: #e8a500; color: #fff; border-radius: 6px;
                 padding: 8px 16px; font-size: 14px; }
  #chat { height: calc(100vh - 150px); overflow-y: auto; padding: 12px 16px; }
  .msg { margin: 8px 0; padding: 10px 12px; border-radius: 12px; line-height: 1.5;
         max-width: 82%; white-space: pre-wrap; word-break: break-word; font-size: 15px; }
  .user { background: #d3e6ff; margin-left: auto; border-bottom-right-radius: 4px; }
  .ai   { background: #fff; margin-right: auto; border-bottom-left-radius: 4px;
          box-shadow: 0 1px 2px rgba(0,0,0,.05); }
  .msg img { max-width: 220px; border-radius: 8px; display: block; margin-top: 4px; }
  #preview { padding: 4px 16px 0; text-align: right; }
  #preview img { max-height: 100px; border-radius: 8px; border: 1px solid #ddd; }
  #preview button { border: 0; background: #e00; color: #fff; border-radius: 50%;
                    width: 20px; height: 20px; margin-left: 4px; }
  #input { position: fixed; left: 0; right: 0; bottom: 0; background: #fff;
           padding: 10px 12px; display: flex; gap: 8px; border-top: 1px solid #e5e5e5; }
  #msg { flex: 1; border: 1px solid #ddd; border-radius: 16px; padding: 10px 14px;
         font-size: 15px; outline: none; resize: none; max-height: 120px;
         font-family: inherit; line-height: 1.4; }
  #attach { border: 1px solid #ddd; background: #fff; border-radius: 50%;
            width: 40px; font-size: 18px; }
  #send { border: 0; background: #2f6fed; color: #fff; border-radius: 20px;
          padding: 0 20px; font-size: 15px; }
  #send:disabled { background: #a7c2f5; }
</style>
</head>
<body>
<header>
  <h3>Claude Code<span class="badge">终端助手</span></h3>
  <button id="clear">清空</button>
</header>
<div id="auth">
  <input id="token" type="password" placeholder="请输入访问口令">
  <button id="authBtn">确认</button>
</div>
<div id="chat"></div>
<div id="preview" style="display:none"></div>
<div id="input">
  <button id="attach" title="发送图片">🖼️</button>
  <textarea id="msg" rows="1" placeholder="发消息给 Claude Code…（回车换行，点发送）"></textarea>
  <button id="send">发送</button>
  <input type="file" id="file" accept="image/*" style="display:none">
</div>
<script>
const chatEl = document.getElementById('chat');
const msgEl = document.getElementById('msg');
const sendBtn = document.getElementById('send');
const authBar = document.getElementById('auth');
const tokenEl = document.getElementById('token');
const attachBtn = document.getElementById('attach');
const fileInput = document.getElementById('file');
const preview = document.getElementById('preview');
const TOKEN_KEY = 'bridge_token';
let token = localStorage.getItem(TOKEN_KEY) || '';
let busy = false;
let selectedImage = null;

authBar.style.display = token ? 'none' : 'flex';

document.getElementById('authBtn').onclick = () => {
  const v = tokenEl.value.trim();
  if (!v) return;
  token = v;
  localStorage.setItem(TOKEN_KEY, v);
  tokenEl.value = '';
  authBar.style.display = 'none';
  msgEl.focus();
};

attachBtn.onclick = () => fileInput.click();
fileInput.onchange = () => {
  const f = fileInput.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => {
    selectedImage = { name: f.name, base64: reader.result.split(',')[1], dataUrl: reader.result };
    preview.style.display = 'block';
    preview.innerHTML = '<img src="' + reader.result + '"><button onclick="clearImage()">✕</button>';
  };
  reader.readAsDataURL(f);
};

function clearImage() {
  selectedImage = null;
  preview.style.display = 'none';
  preview.innerHTML = '';
  fileInput.value = '';
}

function add(role, text) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}

function addImage(role, dataUrl) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  const img = document.createElement('img');
  img.src = dataUrl;
  div.appendChild(img);
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function send() {
  if (busy) return;
  const text = msgEl.value.trim();
  if (!text && !selectedImage) return;
  msgEl.value = '';
  if (text) add('user', text);
  if (selectedImage) addImage('user', selectedImage.dataUrl);
  const imgPayload = selectedImage;
  clearImage();
  const tip = add('ai', '思考中…');
  busy = true;
  sendBtn.disabled = true;

  const payload = {
    message: text,
    image_base64: imgPayload ? imgPayload.base64 : null,
    image_name: imgPayload ? imgPayload.name : null
  };

  async function streamOnce() {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Auth-Token': token },
      body: JSON.stringify(payload)
    });
    if (res.status === 401) {
      token = '';
      localStorage.removeItem(TOKEN_KEY);
      authBar.style.display = 'flex';
      tip.textContent = '口令错误，请重新输入';
      return null;
    }
    if (!res.ok) {
      tip.textContent = '出错：HTTP ' + res.status;
      return null;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let acc = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf('\n\n')) !== -1) {
        const raw = buf.slice(0, i);
        buf = buf.slice(i + 2);
        const line = raw.trim();
        if (!line.startsWith('data:')) continue;
        const p = line.slice(5).trim();
        if (p === '[DONE]') continue;
        try {
          const o = JSON.parse(p);
          if (o.text) {
            acc += o.text;
            tip.textContent = acc;
            chatEl.scrollTop = chatEl.scrollHeight;
          } else if (o.error) {
            acc += (acc ? '\n' : '') + '[错误] ' + o.error;
            tip.textContent = acc;
          }
        } catch (e) {}
      }
    }
    return acc;
  }

  const MAX_RETRY = 2;
  try {
    for (let attempt = 0; attempt <= MAX_RETRY; attempt++) {
      if (attempt > 0) tip.textContent = '⚠️ 网络中断，正在重试 ' + attempt + '/' + MAX_RETRY + '…';
      try {
        const acc = await streamOnce();
        if (acc === null) return;
        if (!acc) tip.textContent = '(无回复)';
        return;
      } catch (e) {
        const m = String((e && e.message) || e);
        const isNet = /network|fetch|failed|NetworkError|abort/i.test(m);
        if (!isNet || attempt === MAX_RETRY) {
          tip.textContent = '⚠️ 网络不稳定，请点发送再试一次';
          return;
        }
      }
    }
  } finally {
    busy = false;
    sendBtn.disabled = false;
  }
}

sendBtn.onclick = send;
msgEl.addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    send();
  }
});
document.getElementById('clear').onclick = async () => {
  chatEl.innerHTML = '';
  try { await fetch('/clear', { method: 'POST', headers: { 'X-Auth-Token': token } }); } catch (e) {}
};
</script>
</body>
</html>
"""

LOG_HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>聊天记录监控</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f5f6f8; color: #222; }
  header { background: #fff; padding: 12px 16px; border-bottom: 1px solid #e5e5e5;
           display: flex; align-items: center; justify-content: space-between; }
  header h3 { margin: 0; font-size: 16px; }
  header a { color: #2f6fed; text-decoration: none; font-size: 14px; }
  #auth { display: flex; gap: 8px; padding: 8px 16px; background: #fff8e6;
          border-bottom: 1px solid #f0e0b0; align-items: center; }
  #auth input { flex: 1; border: 1px solid #ddd; border-radius: 6px; padding: 8px 12px;
                font-size: 14px; outline: none; }
  #auth button { border: 0; background: #e8a500; color: #fff; border-radius: 6px;
                 padding: 8px 16px; font-size: 14px; }
  #chat { padding: 12px 16px; overflow-y: auto; }
  .row { margin: 8px 0; }
  .row .meta { font-size: 11px; color: #999; margin-bottom: 2px; }
  .bubble { padding: 10px 12px; border-radius: 12px; line-height: 1.5;
            max-width: 82%; white-space: pre-wrap; word-break: break-word; font-size: 15px; }
  .user .bubble { background: #d3e6ff; margin-left: auto; border-bottom-right-radius: 4px; }
  .user .meta { text-align: right; }
  .ai .bubble { background: #fff; margin-right: auto; border-bottom-left-radius: 4px;
                box-shadow: 0 1px 2px rgba(0,0,0,.05); }
  .bubble img { max-width: 220px; border-radius: 8px; display: block; margin-top: 4px; }
</style>
</head>
<body>
<header>
  <h3>聊天记录监控 <span style="font-size:12px;color:#999">(每2秒自动刷新)</span></h3>
  <a id="dl" href="#">下载 Excel</a>
</header>
<div id="auth">
  <input id="token" type="password" placeholder="请输入访问口令">
  <button id="authBtn">确认</button>
</div>
<div id="chat"></div>
<script>
const chatEl = document.getElementById('chat');
const authBar = document.getElementById('auth');
const tokenEl = document.getElementById('token');
const dl = document.getElementById('dl');
const TOKEN_KEY = 'bridge_token';
let token = localStorage.getItem(TOKEN_KEY) || '';

authBar.style.display = token ? 'none' : 'flex';
function updDl() { dl.href = '/xlsx?token=' + encodeURIComponent(token); }
updDl();

document.getElementById('authBtn').onclick = () => {
  const v = tokenEl.value.trim();
  if (!v) return;
  token = v;
  localStorage.setItem(TOKEN_KEY, v);
  tokenEl.value = '';
  authBar.style.display = 'none';
  updDl();
  refresh();
};

function render(items) {
  chatEl.innerHTML = '';
  for (const it of items) {
    const row = document.createElement('div');
    row.className = 'row ' + (it.role === '用户' ? 'user' : 'ai');
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = it.time + ' · ' + it.role;
    const b = document.createElement('div');
    b.className = 'bubble';
    b.textContent = it.text;
    if (it.image) {
      const img = document.createElement('img');
      img.src = '/image?token=' + encodeURIComponent(token) + '&p=' + encodeURIComponent(it.image);
      b.appendChild(img);
    }
    row.appendChild(meta);
    row.appendChild(b);
    chatEl.appendChild(row);
  }
  chatEl.scrollTop = chatEl.scrollHeight;
}

async function refresh() {
  if (!token) return;
  try {
    const res = await fetch('/history?token=' + encodeURIComponent(token));
    if (res.status === 401) {
      token = '';
      localStorage.removeItem(TOKEN_KEY);
      authBar.style.display = 'flex';
      return;
    }
    render(await res.json());
  } catch (e) {}
}

refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>
"""


GUIDE_HUB = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>选山 · 徒步摄影攻略</title>
<style>
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         margin: 0; background: #f4f6f2; color: #1f2d21; line-height: 1.6; }
  .hero { background: linear-gradient(135deg, #1b5e20 0%, #2e7d32 55%, #66bb6a 100%);
          color: #fff; padding: 32px 20px 28px; text-align: center; }
  .hero h1 { margin: 0; font-size: 24px; letter-spacing: 1px; }
  .hero p { margin: 8px 0 0; opacity: .9; font-size: 13px; }
  main { max-width: 480px; margin: 0 auto; padding: 20px 16px 40px; }
  a.card { display: block; text-decoration: none; color: inherit; background: #fff;
           border-radius: 16px; padding: 20px; margin-bottom: 16px;
           box-shadow: 0 2px 8px rgba(0,0,0,.08); }
  a.card h2 { margin: 0 0 6px; font-size: 20px; color: #2e7d32; }
  a.card .sub { font-size: 13px; color: #6b7a6b; margin: 0 0 10px; }
  a.card .tags { display: flex; flex-wrap: wrap; gap: 6px; }
  a.card .tag { background: #e8f5e9; color: #2e7d32; border-radius: 12px;
                padding: 2px 10px; font-size: 12px; }
  a.card .go { float: right; color: #2e7d32; font-size: 14px; }
</style>
</head>
<body>
<div class="hero">
  <h1>⛰️ 徒步摄影攻略</h1>
  <p>选一座山，出发</p>
</div>
<main>
  <a class="card" href="/guide/wugong">
    <span class="go">→</span>
    <h2>武功山</h2>
    <p class="sub">江西萍乡 · 沈子村→金顶→发云界 · 草甸云海 · 2 天 1 夜</p>
    <div class="tags">
      <span class="tag">金顶云海</span><span class="tag">银河星空</span><span class="tag">索尼 A7M4</span>
    </div>
  </a>
  <a class="card" href="/guide/emei">
    <span class="go">→</span>
    <h2>峨眉山</h2>
    <p class="sub">四川乐山 · 报国寺→金顶 3079m · 云海佛光 · 2 天 1 夜</p>
    <div class="tags">
      <span class="tag">云海日出</span><span class="tag">佛光</span><span class="tag">索尼 A7M4</span>
    </div>
  </a>
</main>
</body>
</html>
"""


def write_xlsx(path, rows):
    """生成最小 xlsx（四列：时间/角色/内容/图片）。rows: [(时间,角色,内容,图片)]"""
    all_rows = [("时间", "角色", "内容", "图片")] + list(rows)
    sheet = []
    for i, (ts, role, text, img) in enumerate(all_rows, 1):
        sheet.append(
            '<row r="%d">'
            '<c r="A%d" t="inlineStr"><is><t>%s</t></is></c>'
            '<c r="B%d" t="inlineStr"><is><t>%s</t></is></c>'
            '<c r="C%d" t="inlineStr"><is><t>%s</t></is></c>'
            '<c r="D%d" t="inlineStr"><is><t>%s</t></is></c>'
            '</row>' % (i, i, escape(ts), i, escape(role), i, escape(text), i, escape(img or "")))
    sheet_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                 '<sheetData>' + ''.join(sheet) + '</sheetData></worksheet>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          '<sheets><sheet name="聊天记录" sheetId="1" r:id="rId1"/></sheets></workbook>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
               '</Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def load_history():
    global history
    if os.path.exists(JSONL_PATH):
        try:
            with open(JSONL_PATH, "r", encoding="utf-8") as f:
                history = [json.loads(l) for l in f if l.strip()]
        except Exception:
            history = []


def persist():
    try:
        with open(JSONL_PATH, "w", encoding="utf-8") as f:
            for e in history:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    except OSError:
        pass
    try:
        write_xlsx(XLSX_PATH, [(e["time"], e["role"], e["text"], e.get("image", "")) for e in history])
    except Exception:
        pass


def record_exchange(user_text, ts_user, reply, ts_ai, image_path=None):
    with _lock:
        history.append({"time": ts_user, "role": "用户",
                        "text": user_text or "[图片]", "image": image_path or ""})
        history.append({"time": ts_ai, "role": "AI", "text": reply})
        persist()


def save_image(image_base64, image_name):
    ext = os.path.splitext(image_name or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        ext = ".png"
    fname = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ext
    path = os.path.join(IMAGES_DIR, fname)
    with open(path, "wb") as f:
        f.write(base64.b64decode(image_base64))
    return path.replace("\\", "/")


def _safe_kill(proc):
    try:
        if proc and proc.poll() is None:
            proc.kill()
    except Exception:
        pass


def call_claude_stream(text):
    """流式调用 claude，逐段产出文本。产出 (is_error, payload)。"""
    global session_id, _current_proc
    cmd = ["claude", "-p", text, "--output-format", "stream-json",
           "--verbose", "--include-partial-messages",
           "--dangerously-skip-permissions"]
    if session_id:
        cmd += ["--resume", session_id]
    if MODEL:
        cmd += ["--model", MODEL]
    try:
        proc = subprocess.Popen(cmd, cwd=WORKDIR, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, encoding="utf-8",
                                errors="replace",
                                creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception as e:
        yield True, f"启动 claude 失败: {e}"
        return
    _current_proc = proc
    _stderr = []
    def _drain_stderr():
        try:
            for line in proc.stderr:
                _stderr.append(line)
        except Exception:
            pass
    threading.Thread(target=_drain_stderr, daemon=True).start()
    _timer = threading.Timer(300, lambda: _safe_kill(proc))
    _timer.daemon = True
    _timer.start()

    for raw in proc.stdout:
        raw = raw.strip()
        if not raw:
            continue
        try:
            evt = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if evt.get("session_id"):
            session_id = evt["session_id"]
        if evt.get("type") == "stream_event":
            e = evt.get("event") or {}
            if e.get("type") == "content_block_delta":
                d = e.get("delta") or {}
                if d.get("type") == "text_delta" and d.get("text"):
                    yield False, d["text"]
        if evt.get("type") == "result" and evt.get("is_error"):
            yield True, evt.get("result") or "claude 返回错误"
    proc.wait()
    _timer.cancel()
    _current_proc = None
    if proc.returncode != 0:
        err = "".join(_stderr).strip()[:1000]
        yield True, err or f"claude 退出码 {proc.returncode}"


def format_notify(data):
    """把 hook 传来的 JSON 或 {"message":...} 格式化成可读文本。"""
    if not isinstance(data, dict):
        return str(data).strip()
    if data.get("message"):
        return str(data["message"]).strip()
    event = data.get("hook_event_name") or ""
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input")
    if isinstance(ti, dict):
        detail = ti.get("command") or ti.get("file_path") or ti.get("path") or ti.get("pattern") or ""
    else:
        detail = str(ti or "")
    bits = [str(x) for x in (event, tool, str(detail)) if x]
    return " ".join(bits).strip()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        """给每个连接设读写超时，防止慢/死客户端让 sendall 永久阻塞（假死根因）。"""
        try:
            self.request.settimeout(120)
        except Exception:
            pass
        super().setup()

    def _guard(self):
        """入口防护：封禁检查 + 速率限制。返回 True 放行，False 已拦截并写出响应。
        注意：绝不在持有 _guard_lock 时写响应（wfile.write 可能阻塞），否则全局死锁。"""
        ip = self.client_address[0]
        now = time.time()
        blocked = None
        with _guard_lock:
            expire = _ban.get(ip)
            if expire:
                if now < expire:
                    blocked = 403
                else:
                    del _ban[ip]
            if blocked is None:
                times = [t for t in _reqs.get(ip, []) if now - t < RATE_WINDOW]
                if len(times) >= RATE_LIMIT:
                    blocked = 429
                else:
                    times.append(now)
                    _reqs[ip] = times
        if blocked == 403:
            self._json(403, {"error": "请求过于频繁，已暂时限制访问"})
            return False
        if blocked == 429:
            self._json(429, {"error": "请求过于频繁，请稍后再试"})
            return False
        return True

    def _record_fail(self, ip):
        with _guard_lock:
            n = _fails.get(ip, 0) + 1
            if n >= BAN_THRESHOLD:
                _ban[ip] = time.time() + BAN_SECONDS
                _fails.pop(ip, None)
            else:
                _fails[ip] = n

    def _clear_fail(self, ip):
        with _guard_lock:
            _fails.pop(ip, None)

    def do_GET(self):
        if not self._guard():
            return
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            return self._html(HTML)
        if path == "/log":
            return self._html(LOG_HTML)
        if path == "/guide":
            return self._html(GUIDE_HUB)
        if path == "/guide/wugong":
            return self._file(GUIDE_PATH, "text/html; charset=utf-8")
        if path == "/guide/emei" or path == "/emei":
            return self._file(EMEI_PATH, "text/html; charset=utf-8")
        if path == "/history":
            if not self._token_ok():
                return self._json(401, {"error": "访问口令错误"})
            with _lock:
                items = list(history)
            return self._json(200, items)
        if path == "/image":
            if not self._token_ok():
                return self._json(401, {"error": "访问口令错误"})
            p = self._query("p")
            if p and os.path.exists(p) and os.path.isfile(p):
                return self._file(p, self._mime(p))
            return self.send_error(404)
        if path == "/xlsx":
            if not self._token_ok():
                return self._json(401, {"error": "访问口令错误"})
            return self._file(XLSX_PATH, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.send_error(404)

    def do_HEAD(self):
        """响应 Sakura 等反代的 HTTP 探测（HEAD），避免被判为「非 HTTP 服务器」而禁用自动 HTTPS。"""
        if not self._guard():
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        if not self._guard():
            return
        ip = self.client_address[0]
        if self.headers.get("X-Auth-Token") != TOKEN:
            self._record_fail(ip)
            return self._json(401, {"error": "访问口令错误"})
        self._clear_fail(ip)
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length).decode("utf-8")
            data = json.loads(raw) if raw else {}
        except Exception as e:
            return self._json(400, {"error": f"请求解析失败: {e}"})

        if self.path == "/chat":
            text = (data.get("message") or "").strip()
            image_path = None
            if data.get("image_base64"):
                try:
                    image_path = save_image(data["image_base64"], data.get("image_name"))
                except Exception:
                    image_path = None
            prompt = text or "[用户发送了一张图片]"
            if not _proc_sem.acquire(blocking=False):
                return self._json(429, {"error": "当前处理请求过多，请稍后再试"})
            ts_user = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            full = []
            disconnected = False
            try:
                # 注意：流式写响应期间绝不持有 _lock（wfile.write 会阻塞，死锁即假死根因）
                for is_err, payload in call_claude_stream(prompt):
                    ok = self._sse({"error": payload} if is_err else {"text": payload})
                    full.append("[错误] " + payload if is_err else payload)
                    if not ok:
                        disconnected = True
                        break
                    if is_err:
                        break
                if disconnected:
                    _safe_kill(_current_proc)
                self._sse({"done": True})
                reply = "".join(full)
                record_exchange(text, ts_user, reply,
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), image_path)
            finally:
                _proc_sem.release()
            return

        if self.path == "/clear":
            global session_id
            session_id = None
            return self._json(200, {"ok": True})

        if self.path == "/notify":
            msg = format_notify(data) or "(空通知)"
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with _lock:
                history.append({"time": ts, "role": "系统", "text": msg})
                persist()
            return self._json(200, {"ok": True})

        self.send_error(404)

    def _query(self, key):
        qs = ""
        if "?" in self.path:
            qs = self.path.split("?", 1)[1]
        for kv in qs.split("&"):
            if kv.startswith(key + "="):
                from urllib.parse import unquote
                return unquote(kv[len(key) + 1:])
        return ""

    def _token_ok(self):
        ok = self._query("token") == TOKEN
        ip = self.client_address[0]
        if ok:
            self._clear_fail(ip)
        else:
            self._record_fail(ip)
        return ok

    def _mime(self, p):
        ext = os.path.splitext(p)[1].lower()
        return {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}.get(ext[1:], "image/png")

    def _html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype):
        if not os.path.exists(path):
            return self.send_error(404)
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, obj):
        line = "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
        try:
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()
            return True
        except Exception:
            return False

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        try:
            msg = fmt % args
        except Exception:
            msg = str(args)
        # 过滤控制字符/二进制（公网扫描器会发 TLS 原始字节），避免日志变二进制、干扰排查
        msg = "".join(c if c.isprintable() or c in "\n\t" else f"\\x{ord(c):02x}" for c in msg)
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), msg))


def main():
    load_history()
    print(f"Claude Code 桥服务已启动: http://127.0.0.1:{PORT}")
    print(f"手机访问: http://<本机IP>:{PORT}   监控页: http://127.0.0.1:{PORT}/log")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
