#!/usr/bin/env python3
"""Hermes Core 状态页服务 — 极简 HTTP 服务, 提供内核状态 HTML 页面.
监听独立端口 (默认 8648), 手机 App iframe 可正常显示 (HTML 而非 JSON).
纯 stdlib 零依赖.
"""
import json
import os
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CORE_PORT = os.environ.get("CORE_PORT", "8642")
CORE_HOST = "127.0.0.1"
API_KEY = os.environ.get("CORE_API_KEY", "")
LISTEN_PORT = int(os.environ.get("STATUS_PORT", "8648"))
BIND_HOST = os.environ.get("STATUS_HOST", "0.0.0.0")


def _core_health():
    """探测内核 8642 health. 返回 (ok, info)."""
    try:
        req = urllib.request.Request(f"http://{CORE_HOST}:{CORE_PORT}/health", headers={"Authorization": f"Bearer {API_KEY}"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return True, data
    except Exception as e:
        return False, {"error": str(e)}


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Core</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", sans-serif; background:#f5f6fa; margin:0; padding:16px; }}
  .card {{ background:#fff; border-radius:12px; padding:20px; margin-bottom:12px; box-shadow:0 1px 4px rgba(0,0,0,.08); }}
  h1 {{ font-size:20px; margin:0 0 12px; }}
  .status {{ display:inline-block; padding:4px 12px; border-radius:20px; font-size:13px; font-weight:600; }}
  .ok {{ background:#e6f7ec; color:#0e9f4e; }}
  .down {{ background:#fdecec; color:#d93026; }}
  .row {{ display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #f0f0f0; font-size:14px; }}
  .row:last-child {{ border-bottom:none; }}
  .label {{ color:#666; }} .val {{ color:#222; font-family:monospace; }}
  .meta {{ color:#999; font-size:12px; margin-top:16px; text-align:center; }}
</style>
</head>
<body>
  <div class="card">
    <h1>🔧 Hermes Core</h1>
    <span class="status {STATUS_CLS}">{STATUS_TEXT}</span>
    <div style="height:12px"></div>
    <div class="row"><span class="label">状态</span><span class="val">{STATE}</span></div>
    <div class="row"><span class="label">平台</span><span class="val">{PLATFORM}</span></div>
    <div class="row"><span class="label">版本</span><span class="val">{VERSION}</span></div>
    <div class="row"><span class="label">内核端口</span><span class="val">{CORE_PORT}</span></div>
    <div class="row"><span class="label">API 地址</span><span class="val">http://127.0.0.1:{CORE_PORT}</span></div>
  </div>
  <div class="meta">Hermes Core · 本地内核 · 状态页刷新于 {TS}</div>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        ok, info = _core_health()
        if ok:
            status_cls, status_text = "ok", "● 运行中"
            state = "healthy"
            platform = info.get("platform", "-")
            version = info.get("version", "-")
        else:
            status_cls, status_text = "down", "● 未运行"
            state = info.get("error", "unreachable")
            platform = version = "-"
        html = PAGE.format(
            STATUS_CLS=status_cls,
            STATUS_TEXT=status_text,
            STATE=state,
            PLATFORM=platform,
            VERSION=version,
            CORE_PORT=CORE_PORT,
            TS=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class Server(ThreadingHTTPServer):
    allow_reuse_address = True


def main():
    server = Server((BIND_HOST, LISTEN_PORT), Handler)
    print(f"status server on {BIND_HOST}:{LISTEN_PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
