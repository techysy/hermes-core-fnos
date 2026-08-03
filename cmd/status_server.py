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
    ("DASHBOARD_ENABLED", "Dashboard 开关(true/false)", False),
    ("DASHBOARD_USER", "Dashboard 用户名", False),
    ("DASHBOARD_PASSWORD", "Dashboard 密码", True),
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
    """写 gateway.env. 只更新前端提交的字段, 未提交的保留原值 (避免误清空)."""
    if not CONFIG_FILE:
        return False, "CONFIG_FILE 未配置"
    try:
        # 读当前值, 未提交的字段保留原值
        current = _load_config()
        with open(CONFIG_FILE, "w") as f:
            for key, _, _sens in CONFIG_FIELDS:
                if key in data:
                    # 前端提交了 → 用新值 (留空 = 清空该字段)
                    val = data.get(key, "").strip()
                else:
                    # 前端没提交 → 保留原值
                    val = current.get(key, "")
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


def _gateway_status():
    """读取 /health/detailed, 返回消息网关 + 平台状态."""
    try:
        req = urllib.request.Request(f"http://{CORE_HOST}:{CORE_PORT}/health/detailed",
                                     headers={"Authorization": f"Bearer {API_KEY}"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
        gw_state = data.get("gateway_state", "unknown")
        platforms = data.get("platforms", {}) or {}
        connected = [k for k, v in platforms.items() if isinstance(v, dict) and v.get("state") == "connected"]
        return {
            "state": gw_state,
            "platforms": platforms,
            "connected": connected,
            "raw": data,
        }
    except Exception as e:
        return {"state": "unknown", "error": str(e), "platforms": {}, "connected": []}


def _dashboard_status():
    """探测 Hermes 原生 dashboard (9119) 状态."""
    cfg = _load_config()
    enabled = cfg.get("DASHBOARD_ENABLED", "").strip().lower() in ("true", "1", "yes")
    user = cfg.get("DASHBOARD_USER", "") or "admin"
    port = 9119
    ok = False
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/login", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            ok = resp.status == 200
    except Exception:
        ok = False
    return {
        "enabled": enabled,
        "ok": ok,
        "user": user,
        "port": port,
    }


def _llm_status():
    """探测兜底 LLM API 连接状态 (LLM_BASE_URL/v1/models)."""
    cfg = _load_config()
    base = cfg.get("LLM_BASE_URL", "")
    key = cfg.get("LLM_API_KEY", "")
    model = cfg.get("LLM_MODEL", "")
    if not base:
        # 未配置兜底, 显示为"未配置" (用 9Router 或无)
        return {"configured": False, "ok": False, "msg": "未配置兜底 LLM（默认使用 9Router）"}
    url = base.rstrip("/") + "/v1/models"
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            models = [m.get("id", "") for m in data.get("data", [])][:5] if isinstance(data.get("data"), list) else []
            return {"configured": True, "ok": True, "msg": f"连接正常 ({len(data.get('data', []))} 模型)", "model": model, "models": models}
    except Exception as e:
        return {"configured": True, "ok": False, "msg": f"连接失败: {e}", "model": model}


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Core</title>
<style>
  /* 日夜主题 CSS 变量 */
  :root, [data-theme="light"] {{
    --bg: #f5f6fa; --card: #ffffff; --text: #222222; --muted: #666666;
    --border: #e0e0e0; --input-bg: #ffffff; --accent: #2f6fed;
    --ok-bg: #e6f7ec; --ok-text: #0e9f4e; --down-bg: #fdecec; --down-text: #d93026;
    --tab-bg: #ececec; --tab-active: #ffffff; --shadow: rgba(0,0,0,.08);
  }}
  [data-theme="dark"] {{
    --bg: #1a1a1f; --card: #26262e; --text: #e8e8ea; --muted: #9a9aa0;
    --border: #3a3a44; --input-bg: #1e1e24; --accent: #4d8dff;
    --ok-bg: #123524; --ok-text: #34c673; --down-bg: #3a1d1d; --down-text: #ff7a70;
    --tab-bg: #2e2e36; --tab-active: #26262e; --shadow: rgba(0,0,0,.3);
  }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background:var(--bg); color:var(--text); margin:0; padding:16px; -webkit-text-size-adjust:100%; }}
  .topbar {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; flex-wrap:wrap; gap:8px; }}
  .topbar h1 {{ font-size:20px; margin:0; }}
  .topbar-actions {{ display:flex; gap:8px; }}
  .icon-btn {{ padding:8px 12px; border:1px solid var(--border); border-radius:8px; background:var(--card); color:var(--text); font-size:13px; cursor:pointer; }}
  .icon-btn:hover {{ opacity:.85; }}
  .tabs {{ display:flex; gap:6px; margin-bottom:14px; }}
  .tab {{ padding:10px 20px; border-radius:8px; border:none; background:var(--tab-bg); color:var(--muted); font-size:14px; font-weight:600; cursor:pointer; }}
  .tab.active {{ background:var(--tab-active); color:var(--accent); box-shadow:0 1px 3px var(--shadow); }}
  .tab-panel {{ display:none; }}
  .tab-panel.active {{ display:block; }}
  .card {{ background:var(--card); border-radius:12px; padding:20px; margin-bottom:12px; box-shadow:0 1px 4px var(--shadow); }}
  h2 {{ font-size:15px; margin:16px 0 8px; color:var(--text); }}
  .status {{ display:inline-block; padding:4px 12px; border-radius:20px; font-size:13px; font-weight:600; }}
  .ok {{ background:var(--ok-bg); color:var(--ok-text); }}
  .down {{ background:var(--down-bg); color:var(--down-text); }}
  .row {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; padding:8px 0; border-bottom:1px solid var(--border); font-size:14px; }}
  .row:last-child {{ border-bottom:none; }}
  .label {{ color:var(--muted); flex-shrink:0; }}
  .val {{ color:var(--text); font-family:monospace; word-break:break-all; text-align:right; }}
  .meta {{ color:var(--muted); font-size:12px; margin-top:16px; text-align:center; }}
  label {{ display:block; font-size:13px; color:var(--muted); margin:10px 0 4px; }}
  input {{ width:100%; padding:10px 12px; border:1px solid var(--border); border-radius:8px; font-size:16px; box-sizing:border-box; background:var(--input-bg); color:var(--text); }}
  input:focus {{ outline:none; border-color:var(--accent); box-shadow:0 0 0 2px rgba(47,111,237,.15); }}
  button {{ margin-top:16px; padding:12px 16px; border:none; border-radius:8px; font-size:15px; cursor:pointer; font-weight:500; }}
  .primary {{ background:var(--accent); color:#fff; width:100%; }}
  .warn {{ background:var(--card); color:var(--text); border:1px solid var(--border); width:100%; }}
  button:active {{ opacity:.85; }}
  .msg {{ margin-top:12px; padding:10px; border-radius:8px; font-size:13px; display:none; word-break:break-all; }}
  .msg.ok {{ background:var(--ok-bg); color:var(--ok-text); display:block; }}
  .msg.err {{ background:var(--down-bg); color:var(--down-text); display:block; }}
  .btn-row {{ display:flex; gap:10px; margin-top:16px; }}
  .btn-row button {{ margin-top:0; flex:1; }}
  /* 移动端响应式 */
  @media (max-width: 480px) {{
    body {{ padding:10px; }}
    .card {{ padding:16px; border-radius:10px; margin-bottom:10px; }}
    h1 {{ font-size:18px; }}
    .row {{ font-size:14px; padding:7px 0; }}
    input {{ font-size:16px; padding:12px; }}  /* ≥16px 防 iOS 自动缩放 */
    button {{ font-size:15px; padding:14px; }}  /* 触控友好 */
    .btn-row {{ flex-direction:column; gap:8px; }}
    .meta {{ font-size:11px; }}
    .tab {{ padding:8px 14px; font-size:13px; }}
  }}
  @media (max-width: 320px) {{
    .row {{ flex-direction:column; gap:2px; }}
    .val {{ text-align:left; }}
  }}
</style>
</head>
<body data-theme="light">
  <div class="topbar">
    <h1>🔧 Hermes Core</h1>
    <div class="topbar-actions">
      <button class="icon-btn" onclick="toggleLang()" id="btn-lang">🌐 EN</button>
      <button class="icon-btn" onclick="toggleTheme()" id="btn-theme">🌙</button>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" data-tab="status" onclick="switchTab('status')" data-i18n="tab-status">状态</button>
    <button class="tab" data-tab="config" onclick="switchTab('config')" data-i18n="tab-config">配置</button>
  </div>

  <!-- 状态标签 -->
  <div class="tab-panel active" id="panel-status">
  <div class="card">
    <h1>🔧 <span data-i18n="core-status">内核状态</span></h1>
    <span class="status {STATUS_CLS}">{STATUS_TEXT}</span>
    <div style="height:12px"></div>
    <div class="row"><span class="label" data-i18n="state">状态</span><span class="val">{STATE}</span></div>
    <div class="row"><span class="label" data-i18n="platform">平台</span><span class="val">{PLATFORM}</span></div>
    <div class="row"><span class="label" data-i18n="version">版本</span><span class="val">{VERSION}</span></div>
    <div class="row"><span class="label" data-i18n="core-port">内核端口</span><span class="val">{CORE_PORT}</span></div>
    <div class="row"><span class="label" data-i18n="api-addr">API 地址</span><span class="val">http://127.0.0.1:{CORE_PORT}</span></div>
  </div>

  <div class="card">
    <h2>📡 <span data-i18n="gateway">消息网关</span></h2>
    <span class="status {GW_CLS}">{GW_TEXT}</span>
    <div style="height:12px"></div>
    {GW_PLATFORMS}
  </div>

  <div class="card">
    <h2>🧠 <span data-i18n="fallback-llm">兜底 LLM</span></h2>
    <span class="status {LLM_CLS}">{LLM_TEXT}</span>
    <div style="height:12px"></div>
    {LLM_ROWS}
  </div>

  <div class="card">
    <h2>📊 <span data-i18n="dashboard">Dashboard</span></h2>
    <span class="status {DASH_CLS}">{DASH_TEXT}</span>
    <div style="height:12px"></div>
    <div class="row"><span class="label" data-i18n="state">状态</span><span class="val">{DASH_DETAIL}</span></div>
    <div class="row"><span class="label" data-i18n="user">用户</span><span class="val">{DASH_USER}</span></div>
    <div class="row"><span class="label" data-i18n="port">端口</span><span class="val">{DASH_PORT}</span></div>
  </div>
  </div>

  <!-- 配置标签 -->
  <div class="tab-panel" id="panel-config">
  <div class="card">
    <h2>⚙️ <span data-i18n="basic-config">基础配置</span></h2>
    <p style="font-size:12px;color:var(--muted);margin:0 0 8px;" data-i18n="config-hint">修改后点击保存，再点"重启内核"生效。敏感项已脱敏显示。</p>
    <div id="msg" class="msg"></div>
    <form id="cfgform">
      {FORM_FIELDS}
    </form>
    <div class="btn-row">
      <button class="primary" onclick="saveConfig()" data-i18n="save-config">💾 保存配置</button>
      <button class="warn" onclick="restartCore()" data-i18n="restart">🔄 重启内核</button>
    </div>
    <p style="font-size:12px;color:var(--muted);margin:12px 0 0;line-height:1.5;" data-i18n="restart-hint">
      ℹ️ 重启内核会同时重启 <b>消息网关</b>（Feishu/Telegram/微信等平台连接）与 cron 调度，消息平台短暂断开后自动恢复。
    </p>
  </div>
  </div>

  <div class="meta">Hermes Core · 本地内核 · {TS}</div>

<script>
const HERMES_AUTH = {AUTH_TOKEN};
const I18N = {{
  zh: {{
    'tab-status':'状态','tab-config':'配置','core-status':'内核状态','state':'状态','platform':'平台',
    'version':'版本','core-port':'内核端口','api-addr':'API 地址','gateway':'消息网关','fallback-llm':'兜底 LLM',
    'dashboard':'Dashboard','user':'用户','port':'端口','basic-config':'基础配置','config-hint':'修改后点击保存，再点"重启内核"生效。敏感项已脱敏显示。',
    'save-config':'💾 保存配置','restart':'🔄 重启内核','restart-hint':'ℹ️ 重启内核会同时重启 消息网关 与 cron 调度',
    'saved':'✅ 配置已保存，请点"重启内核"生效','save-fail':'❌ 保存失败: ','restarting':'🔄 内核正在重启，几秒后刷新页面查看状态','restart-fail':'❌ 重启失败: ',
    'running':'● 运行中','stopped':'● 已停止','healthy':'healthy','unconfigured':'○ 未配置'
  }},
  en: {{
    'tab-status':'Status','tab-config':'Config','core-status':'Core Status','state':'State','platform':'Platform',
    'version':'Version','core-port':'Core Port','api-addr':'API Address','gateway':'Message Gateway','fallback-llm':'Fallback LLM',
    'dashboard':'Dashboard','user':'User','port':'Port','basic-config':'Basic Config','config-hint':'Edit then click Save, then Restart Core to apply. Sensitive fields are masked.',
    'save-config':'💾 Save Config','restart':'🔄 Restart Core','restart-hint':'ℹ️ Restarting the core also restarts the message gateway and cron scheduler',
    'saved':'✅ Config saved, click "Restart Core" to apply','save-fail':'❌ Save failed: ','restarting':'🔄 Core restarting, refresh in a few seconds','restart-fail':'❌ Restart failed: ',
    'running':'● Running','stopped':'● Stopped','healthy':'healthy','unconfigured':'○ Not configured'
  }}
}};
let currentLang = localStorage.getItem('hermes_lang') || 'zh';
let currentTheme = localStorage.getItem('hermes_theme') || 'light';

function applyI18n() {{
  document.querySelectorAll('[data-i18n]').forEach(el => {{
    const key = el.dataset.i18n;
    if (I18N[currentLang][key]) el.textContent = I18N[currentLang][key];
  }});
  document.getElementById('btn-lang').textContent = currentLang === 'zh' ? '🌐 EN' : '🌐 中文';
  // 更新动态生成的表单 label/状态 (通过 data-i18n 无法覆盖, 用替换文本)
  document.querySelectorAll('label').forEach(l => {{
    // label 文本由后端生成, i18n 主要覆盖静态部分
  }});
}}
function toggleLang() {{
  currentLang = currentLang === 'zh' ? 'en' : 'zh';
  localStorage.setItem('hermes_lang', currentLang);
  applyI18n();
}}
function toggleTheme() {{
  currentTheme = currentTheme === 'light' ? 'dark' : 'light';
  localStorage.setItem('hermes_theme', currentTheme);
  document.body.dataset.theme = currentTheme;
  document.getElementById('btn-theme').textContent = currentTheme === 'light' ? '🌙' : '☀️';
}}
function switchTab(tab) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + tab));
}}

async function api(path, method, body) {{
  const headers = {{ 'Content-Type': 'application/json' }};
  if (HERMES_AUTH) headers['Authorization'] = 'Bearer ' + HERMES_AUTH;
  const res = await fetch(path, {{
    method,
    headers,
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
  const fd = new FormData(form);
  // 敏感字段留空 = 不修改 (保留原值)
  const sensitive = ['API_SERVER_KEY', 'ROUTER_API_KEY', 'LLM_API_KEY', 'DASHBOARD_PASSWORD'];
  const data = Object.fromEntries(
    [...fd.entries()].filter(([k, v]) => !(sensitive.includes(k) && !v.trim()))
  );
  const r = await api('/api/config', 'POST', data);
  if (r.ok) showMsg(I18N[currentLang]['saved']);
  else showMsg(I18N[currentLang]['save-fail'] + (r.error || ''), true);
}}
async function restartCore() {{
  const r = await api('/api/restart', 'POST', {{}});
  if (r.ok) showMsg(I18N[currentLang]['restarting']);
  else showMsg(I18N[currentLang]['restart-fail'] + (r.error || ''), true);
}}
// 初始化
document.body.dataset.theme = currentTheme;
document.getElementById('btn-theme').textContent = currentTheme === 'light' ? '🌙' : '☀️';
applyI18n();
</script>
</body>
</html>
"""


def _form_fields(cfg):
    out = []
    for key, label, sensitive in CONFIG_FIELDS:
        val = cfg.get(key, "")
        if sensitive:
            # 敏感字段: 不预填真值, placeholder 显示脱敏值 (需重输才改)
            shown = _mask(val) if val else "未设置"
            ph = f"当前值: {shown}（留空则不改）"
            out.append(f'<label>{label}</label>')
            out.append(f'<input type="text" name="{key}" placeholder="{ph}" value="" autocomplete="off">')
        else:
            # 非敏感字段: 预填当前值, 手机直接改
            shown = val
            out.append(f'<label>{label}</label>')
            out.append(f'<input type="text" name="{key}" value="{shown}" autocomplete="off">')
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

        # 消息网关状态
        gw = _gateway_status()
        if gw.get("state") == "running":
            gw_cls, gw_text = "ok", "● 运行中"
        elif gw.get("state") == "unknown" and not gw.get("platforms"):
            gw_cls, gw_text = "down", "● 未知"
        else:
            gw_cls, gw_text = "down", "● " + str(gw.get("state", "未知"))
        gw_platforms = []
        plats = gw.get("platforms", {})
        if plats:
            for name, p in plats.items():
                pstate = p.get("state", "?") if isinstance(p, dict) else "?"
                if isinstance(p, dict) and p.get("state") == "connected":
                    ptext = f'{name} <span class="ok" style="font-size:11px">● 在线</span>'
                else:
                    err = p.get("error_message") or (p.get("error_code") or "") if isinstance(p, dict) else ""
                    ptext = f'{name} <span class="down" style="font-size:11px">● {pstate}</span>'
                gw_platforms.append(f'<div class="row"><span class="label">{ptext}</span></div>')
        else:
            gw_platforms.append('<div class="row"><span class="label" style="color:#999">未检测到平台</span></div>')

        # 兜底 LLM 状态
        llm = _llm_status()
        if llm.get("ok"):
            llm_cls, llm_text = "ok", "● 连接正常"
        elif llm.get("configured"):
            llm_cls, llm_text = "down", "● 连接失败"
        else:
            llm_cls, llm_text = "down", "○ 未配置"
        llm_rows = []
        llm_rows.append(f'<div class="row"><span class="label">状态</span><span class="val">{llm.get("msg", "")}</span></div>')
        if llm.get("model"):
            llm_rows.append(f'<div class="row"><span class="label">模型</span><span class="val">{llm["model"]}</span></div>')
        if llm.get("models"):
            llm_rows.append(f'<div class="row"><span class="label">可用模型</span><span class="val">{"，".join(llm["models"])}</span></div>')

        # Dashboard 状态
        dash = _dashboard_status()
        if not dash.get("enabled"):
            dash_cls, dash_text, dash_detail = "down", "○ 未启用", "配置 DASHBOARD_ENABLED=true 启用"
        elif dash.get("ok"):
            dash_cls, dash_text, dash_detail = "ok", "● 运行中", "运行中"
        else:
            dash_cls, dash_text, dash_detail = "down", "● 已启用未运行", "未运行（重启内核生效）"
        dash_user = dash.get("user", "-")
        dash_port = dash.get("port", 9119)

        cfg = _load_config()
        html = PAGE.format(
            STATUS_CLS=status_cls,
            STATUS_TEXT=status_text,
            STATE=state,
            PLATFORM=platform,
            VERSION=version,
            CORE_PORT=CORE_PORT,
            GW_CLS=gw_cls,
            GW_TEXT=gw_text,
            GW_PLATFORMS="\n".join(gw_platforms),
            LLM_CLS=llm_cls,
            LLM_TEXT=llm_text,
            LLM_ROWS="\n".join(llm_rows),
            DASH_CLS=dash_cls,
            DASH_TEXT=dash_text,
            DASH_DETAIL=dash_detail,
            DASH_USER=dash_user,
            DASH_PORT=dash_port,
            FORM_FIELDS=_form_fields(cfg),
            AUTH_TOKEN=json.dumps(API_KEY),   # 注入鉴权 token 到前端 JS
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
