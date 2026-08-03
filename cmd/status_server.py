#!/usr/bin/env python3
"""Hermes Core 状态页 + 配置服务.
提供:
- GET /            → 状态页 + 配置表单 (脱敏显示当前配置)
- POST /api/config → 保存配置到 gateway.env (需 Bearer API key 鉴权)
- POST /api/restart → 重启内核 (需 Bearer API key 鉴权)
纯 stdlib 零依赖. 监听独立端口 (默认 8648).
"""
import json
import os
import re
import subprocess
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CORE_PORT = os.environ.get("CORE_PORT", "8642")
CORE_HOST = "127.0.0.1"
API_KEY = os.environ.get("CORE_API_KEY", "")
LISTEN_PORT = int(os.environ.get("STATUS_PORT", "8648"))
BIND_HOST = os.environ.get("STATUS_HOST", "0.0.0.0")
CONFIG_FILE = os.environ.get("CORE_CONFIG", "")
CMD_MAIN = os.environ.get("CORE_CMD", "")

# 可配置字段: (gateway.env key, 表单 label, 是否敏感)
CONFIG_FIELDS = [
    ("API_SERVER_HOST", "监听地址", False),
    ("API_SERVER_PORT", "API 端口", False),
    ("API_SERVER_KEY", "API Key", True),
    ("ROUTER_API_KEY", "9Router API Key", True),
    ("LLM_BASE_URL", "兜底 LLM Base URL", False),
    ("LLM_API_KEY", "兜底 LLM Token", True),
    ("LLM_MODEL", "兜底模型名", False),
]


def _mask(v):
    """脱敏: 保留前后几位, 中间省略."""
    v = v or ""
    if len(v) <= 6:
        return "***"
    return v[:3] + "..." + v[-3:]


def _load_config():
    """读取 gateway.env. 返回 dict."""
    cfg = {}
    if CONFIG_FILE and os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
        except Exception:
            pass
    return cfg


def _save_config(data):
    """写 gateway.env."""
    if not CONFIG_FILE:
        return False, "CONFIG_FILE 未配置"
    try:
        with open(CONFIG_FILE, "w") as f:
            for key, _, _sens in CONFIG_FIELDS:
                val = data.get(key, "")
                f.write(f'{key}="{val}"\n')
        os.chmod(CONFIG_FILE, 0o600)
        return True, "saved"
    except Exception as e:
        return False, str(e)


def _do_restart():
    """调用 cmd/main restart."""
    if not CMD_MAIN or not os.path.exists(CMD_MAIN):
        return False, "cmd/main 未配置"
    try:
        env = os.environ.copy()
        env["TRIM_APPNAME"] = os.environ.get("TRIM_APPNAME", "HermesCore")
        # 后台执行 restart (延迟, 避免杀掉自己)
        subprocess.Popen(["bash", CMD_MAIN, "restart"], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True, "restarting"
    except Exception as e:
        return False, str(e)


def _core_health():
    try:
        req = urllib.request.Request(f"http://{CORE_HOST}:{CORE_PORT}/health",
                                     headers={"Authorization": f"Bearer {API_KEY}"})
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
  h2 {{ font-size:15px; margin:16px 0 8px; color:#333; }}
  .status {{ display:inline-block; padding:4px 12px; border-radius:20px; font-size:13px; font-weight:600; }}
  .ok {{ background:#e6f7ec; color:#0e9f4e; }}
  .down {{ background:#fdecec; color:#d93026; }}
  .row {{ display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #f0f0f0; font-size:14px; }}
  .row:last-child {{ border-bottom:none; }}
  .label {{ color:#666; }} .val {{ color:#222; font-family:monospace; }}
  .meta {{ color:#999; font-size:12px; margin-top:16px; text-align:center; }}
  label {{ display:block; font-size:13px; color:#666; margin:10px 0 4px; }}
  input {{ width:100%; padding:8px 10px; border:1px solid #ddd; border-radius:8px; font-size:14px; box-sizing:border-box; }}
  button {{ margin-top:16px; padding:10px 16px; border:none; border-radius:8px; font-size:14px; cursor:pointer; }}
  .primary {{ background:#2f6fed; color:#fff; }}
  .warn {{ background:#f5f5f5; color:#333; border:1px solid #ddd; }}
  .msg {{ margin-top:12px; padding:10px; border-radius:8px; font-size:13px; display:none; }}
  .msg.ok {{ background:#e6f7ec; color:#0e9f4e; display:block; }}
  .msg.err {{ background:#fdecec; color:#d93026; display:block; }}
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

  <div class="card">
    <h2>⚙️ 基础配置</h2>
    <p style="font-size:12px;color:#999;margin:0 0 8px;">修改后点击保存，再点"重启内核"生效。敏感项已脱敏显示。</p>
    <div id="msg" class="msg"></div>
    <form id="cfgform">
      {FORM_FIELDS}
    </form>
    <button class="primary" onclick="saveConfig()">💾 保存配置</button>
    <button class="warn" onclick="restartCore()">🔄 重启内核</button>
  </div>

  <div class="meta">Hermes Core · 本地内核 · {TS}</div>

<script>
async function api(path, method, body) {{
  const res = await fetch(path, {{
    method,
    headers: {{ 'Content-Type': 'application/json' }},
    body: body ? JSON.stringify(body) : undefined
  }});
  const data = await res.json().catch(() => ({{}}));
  return {{ ok: res.ok, ...data }};
}}
function showMsg(text, isErr) {{
  const el = document.getElementById('msg');
  el.textContent = text;
  el.className = 'msg ' + (isErr ? 'err' : 'ok');
}}
async function saveConfig() {{
  const form = document.getElementById('cfgform');
  const data = Object.fromEntries(new FormData(form).entries());
  const r = await api('/api/config', 'POST', data);
  if (r.ok) showMsg('✅ 配置已保存，请点"重启内核"生效');
  else showMsg('❌ 保存失败: ' + (r.error || ''), true);
}}
async function restartCore() {{
  const r = await api('/api/restart', 'POST', {{}});
  if (r.ok) showMsg('🔄 内核正在重启，几秒后刷新页面查看状态');
  else showMsg('❌ 重启失败: ' + (r.error || ''), true);
}}
</script>
</body>
</html>
"""


def _form_fields(cfg):
    out = []
    for key, label, sensitive in CONFIG_FIELDS:
        val = cfg.get(key, "")
        shown = _mask(val) if sensitive else val
        ph = "(当前值: " + shown + ")" if val else "(未设置)"
        out.append(f'<label>{label}</label>')
        out.append(f'<input type="text" name="{key}" placeholder="{ph}" value="">')
    return "\n".join(out)


class Handler(BaseHTTPRequestHandler):
    def _check_auth(self):
        """Bearer API key 鉴权."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer ") and auth[7:] == API_KEY:
            return True
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": False, "error": "unauthorized"}).encode())
        return False

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/":
            self._render_page()
        elif self.path == "/api/config":
            if not self._check_auth():
                return
            self._json({"ok": True, "config": _load_config()})
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        if self.path == "/api/config":
            if not self._check_auth():
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length).decode()) if length else {}
            except Exception:
                data = {}
            # 只接受白名单字段
            allowed = {k for k, _, _ in CONFIG_FIELDS}
            clean = {k: (v or "").strip() for k, v in data.items() if k in allowed}
            ok, err = _save_config(clean)
            self._json({"ok": ok, "error": err} if not ok else {"ok": True})
        elif self.path == "/api/restart":
            if not self._check_auth():
                return
            ok, err = _do_restart()
            self._json({"ok": ok, "error": err} if not ok else {"ok": True})
        else:
            self._json({"ok": False, "error": "not found"}, 404)

    def _render_page(self):
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
        cfg = _load_config()
        html = PAGE.format(
            STATUS_CLS=status_cls,
            STATUS_TEXT=status_text,
            STATE=state,
            PLATFORM=platform,
            VERSION=version,
            CORE_PORT=CORE_PORT,
            FORM_FIELDS=_form_fields(cfg),
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
