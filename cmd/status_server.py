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

# 状态页 UI 版本 — 动态从已安装 manifest 读取 (替代硬编码, 升级即更新)
# 读不到时回退为空 (footer 不显示版本号)
def _app_version():
    """从已安装的 manifest 动态读取 HermesCore 应用版本.
    返回如 '0.4.6', 读不到时返回 '' (footer 不显示版本号).
    """
    candidates = []
    if CMD_MAIN:
        # CMD_MAIN 指向 <app_dir>/cmd/main → manifest 在上级目录
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(CMD_MAIN)), "manifest"))
    candidates += [
        "/var/apps/HermesCore/manifest",
        "/vol4/@appcenter/HermesCore/manifest",
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("version") and "=" in line:
                        return line.split("=", 1)[1].strip()
        except (OSError, IOError):
            continue
    return ""


STATUS_VER = _app_version()

# 可配置字段: (gateway.env key, 表单 label, 是否敏感, 分组)
# 分组: core=内核 / llm=LLM连接 / dash=Dashboard / feishu=飞书 / wechat=微信
CONFIG_FIELDS = [
    ("API_SERVER_HOST", "监听地址", False, "core"),
    ("API_SERVER_PORT", "API 端口", False, "core"),
    ("API_SERVER_KEY", "API Key", True, "core"),
    ("ROUTER_API_KEY", "9Router API Key", True, "llm"),
    ("DEEPSEEK_API_KEY", "DeepSeek API Key", True, "llm"),
    ("XIAOMI_API_KEY", "Xiaomi MiMo API Key", True, "llm"),
    ("LLM_BASE_URL", "默认 LLM Base URL", False, "llm"),
    ("LLM_API_KEY", "默认 LLM Token", True, "llm"),
    ("LLM_MODEL", "默认模型名", False, "llm"),
    ("DASHBOARD_ENABLED", "Dashboard 开关(true/false)", False, "dash"),
    ("DASHBOARD_USER", "Dashboard 用户名", False, "dash"),
    ("DASHBOARD_PASSWORD", "Dashboard 密码", True, "dash"),
    ("FEISHU_APP_ID", "飞书应用 App ID", False, "feishu"),
    ("FEISHU_APP_SECRET", "飞书应用 Secret", True, "feishu"),
    ("FEISHU_VERIFICATION_TOKEN", "飞书验证 Token(验证码)", True, "feishu"),
    ("FEISHU_ENCRYPT_KEY", "飞书加密 Key", True, "feishu"),
    ("WEIXIN_ACCOUNT_ID", "微信账号 ID", False, "wechat"),
    ("WEIXIN_TOKEN", "微信 Token(验证码)", True, "wechat"),
]

# 配置分组标签
CONFIG_GROUPS = {
    "core": ("🔧 内核", "core"),
    "llm": ("🧠 LLM 连接", "llm"),
    "dash": ("📊 Dashboard", "dash"),
    "feishu": ("💬 飞书", "feishu"),
    "wechat": ("💬 微信", "wechat"),
}

# 模型供应商 (参考 9Router providers 页)
# key: 标识, name: 名称, ico: 图标, env: API key 的 gateway.env 字段, default: 是否默认
# bg: 图标背景色, desc: 描述
MODEL_PROVIDERS = [
    {"key": "9router", "name": "9Router", "ico": "🔧", "env": "ROUTER_API_KEY",
     "default": True, "local": True, "bg": "#2f6fed", "desc": "本地代理 (本机 :20128)"},
    {"key": "deepseek", "name": "DeepSeek", "ico": "🐋", "env": "DEEPSEEK_API_KEY",
     "default": False, "local": False, "bg": "#4d6bfe", "desc": "DeepSeek API"},
    {"key": "mimo", "name": "Xiaomi MiMo", "ico": "📱", "env": "XIAOMI_API_KEY",
     "default": False, "local": False, "bg": "#ff6900", "desc": "Xiaomi MiMo API"},
]

# 供应商 base_url (用于生成 config.yaml custom_providers)
MODEL_PROVIDER_URLS = {
    "9router": "http://127.0.0.1:20128/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "mimo": "https://api.xiaomimimo.com/v1",
}


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
        # Dashboard 联动: 配置了用户名/密码则自动启用 (无需单独开开关)
        if data.get("DASHBOARD_USER", "").strip() or data.get("DASHBOARD_PASSWORD", "").strip():
            data = dict(data)
            data["DASHBOARD_ENABLED"] = "true"
        with open(CONFIG_FILE, "w") as f:
            for key, _, _sens, _grp in CONFIG_FIELDS:
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


def _chat_proxy(messages, stream=False):
    """代理聊天请求到本机 api_server (8642) 的 /v1/chat/completions.
    stream=True 时返回生成器 (逐块 yield 文本); 否则返回完整 reply.
    """
    if not messages:
        if stream:
            return iter([]), None
        return None, "no messages"
    cfg = _load_config()
    api_key = cfg.get("API_SERVER_KEY", "")
    model = cfg.get("LLM_MODEL", "") or "default"
    base = os.environ.get("CORE_HOST", "127.0.0.1")
    port = os.environ.get("CORE_PORT", "8642")
    url = f"http://{base}:{port}/v1/chat/completions"
    body = json.dumps({"model": model, "messages": messages, "stream": stream}).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        resp = urllib.request.urlopen(req, timeout=300)
    except Exception as e:
        if stream:
            return iter([]), f"连接失败: {e}"
        return None, str(e)

    if not stream:
        try:
            data = json.loads(resp.read().decode())
            reply = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return reply, None
        except Exception as e:
            return None, f"解析失败: {e}"

    # 流式: 生成器逐行解析 SSE, yield 文本增量
    captured_model = [""]

    def gen():
        try:
            for raw in resp:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    if not captured_model[0]:
                        captured_model[0] = chunk.get("model", "") or model
                    delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if delta:
                        yield delta
                except Exception:
                    continue
        except Exception:
            pass

    return gen(), None, captured_model


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
    """探测默认 LLM API 连接状态 (LLM_BASE_URL/v1/models)."""
    cfg = _load_config()
    base = cfg.get("LLM_BASE_URL", "")
    key = cfg.get("LLM_API_KEY", "")
    model = cfg.get("LLM_MODEL", "")
    if not base:
        # 未配置兜底, 显示为"未配置" (用 9Router 或无)
        return {"configured": False, "ok": False, "msg": "未配置默认 LLM（默认使用 9Router）"}
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
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; background:var(--bg); color:var(--text); margin:0; -webkit-text-size-adjust:100%; }}
  /* 侧边栏布局 (参考 9Router) */
  .layout {{ display:flex; min-height:100vh; }}
  .sidebar {{ width:200px; background:var(--card); border-right:1px solid var(--border); padding:16px 10px; flex-shrink:0; }}
  .sidebar-brand {{ display:flex; align-items:center; gap:8px; padding:0 8px 16px; border-bottom:1px solid var(--border); margin-bottom:12px; }}
  .sidebar-brand .logo {{ width:28px; height:28px; border-radius:8px; background:var(--accent); display:flex; align-items:center; justify-content:center; font-size:16px; }}
  .sidebar-brand .name {{ font-size:14px; font-weight:700; }}
  .sidebar-brand .ver {{ font-size:11px; color:var(--muted); }}
  .nav-item {{ display:flex; align-items:center; gap:8px; padding:10px 12px; border-radius:8px; cursor:pointer; font-size:13px; color:var(--muted); margin-bottom:2px; }}
  .nav-item:hover {{ background:var(--tab-bg); }}
  .nav-item.active {{ background:var(--ok-bg); color:var(--ok-text); font-weight:600; }}
  .nav-item .ico {{ font-size:15px; }}
  .nav-section {{ font-size:11px; color:var(--muted); padding:12px 12px 4px; text-transform:uppercase; letter-spacing:.5px; }}
  .main {{ flex:1; padding:16px; min-width:0; }}
  .topbar {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; gap:8px; }}
  .topbar h1 {{ font-size:20px; margin:0; }}
  .topbar-actions {{ display:flex; gap:8px; }}
  .icon-btn {{ padding:8px 12px; border:1px solid var(--border); border-radius:8px; background:var(--card); color:var(--text); font-size:13px; cursor:pointer; }}
  .icon-btn:hover {{ opacity:.85; }}
  .hamburger {{ display:none; padding:8px 12px; border:1px solid var(--border); border-radius:8px; background:var(--card); color:var(--text); font-size:16px; cursor:pointer; }}
  .sidebar-overlay {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.4); z-index:40; }}
  /* 移动端: 汉堡收起侧栏 */
  @media (max-width: 768px) {{
    .hamburger {{ display:block; }}
    .sidebar {{ position:fixed; left:-200px; top:0; bottom:0; z-index:50; transition:left .2s; }}
    .sidebar.open {{ left:0; }}
    .sidebar-overlay.show {{ display:block; }}
    .main {{ padding:12px; }}
  }}
  .card {{ background:var(--card); border-radius:12px; padding:20px; margin-bottom:12px; box-shadow:0 1px 4px var(--shadow); }}
  /* 配置区块 — 分组独立卡片 */
  .cfg-section {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px 18px; margin-bottom:14px; }}
  .cfg-section-title {{ display:flex; align-items:center; gap:8px; font-size:14px; font-weight:700; color:var(--text); margin-bottom:12px; padding-bottom:8px; border-bottom:1px solid var(--border); }}
  .cfg-section .hint {{ font-size:11px; color:var(--muted); margin-top:10px; }}
  .cfg-section input {{ margin-bottom:2px; }}
  /* 配置字段：内核监听地址+端口 一排 */
  .field-row {{ display:flex; gap:12px; }}
  .field-col {{ flex:1; min-width:0; }}
  .field-col label {{ display:block; font-size:12px; color:var(--muted); margin-bottom:4px; }}
  .field-col input {{ width:100%; }}
  /* Dashboard 开关 (switch) */
  .switch-wrap {{ display:flex; align-items:center; gap:10px; margin-bottom:2px; }}
  .switch {{ position:relative; width:48px; height:26px; border-radius:13px; background:var(--border); border:none; cursor:pointer; transition:background .2s; padding:0; }}
  .switch .knob {{ position:absolute; top:3px; left:3px; width:20px; height:20px; border-radius:50%; background:#fff; transition:left .2s; box-shadow:0 1px 3px rgba(0,0,0,.3); }}
  .switch.on {{ background:var(--accent); }}
  .switch.on .knob {{ left:25px; }}
  .switch-text {{ font-size:13px; color:var(--text); }}
  /* 默认模型卡片 */
  .dm-current {{ font-size:13px; color:var(--text); background:var(--input-bg); border:1px solid var(--border); border-radius:8px; padding:8px 10px; margin-bottom:10px; word-break:break-all; }}
  .dm-input {{ width:100%; padding:8px 10px; border:1px solid var(--border); border-radius:8px; background:var(--input-bg); color:var(--text); font-size:13px; box-sizing:border-box; }}
  select.dm-input {{ cursor:pointer; }}
  /* 聊天窗口 */
  .chat-card {{ display:flex; flex-direction:column; height:calc(100vh - 140px); min-height:400px; }}
  .chat-msgs {{ flex:1; overflow-y:auto; padding:10px; background:var(--input-bg); border-radius:8px; margin-bottom:10px; }}
  .chat-msg {{ margin-bottom:8px; max-width:70%; width:fit-content; min-width:40px; padding:8px 12px; font-size:14px; line-height:1.5; word-break:break-word; overflow-wrap:break-word; white-space:pre-wrap; }}
  /* 微信风格: 自己(右,绿) / 对方(左,白) */
  .chat-msg.user {{ margin-left:auto; background:#95ec69; color:#000; border-top-right-radius:4px; border-top-left-radius:12px; border-bottom-left-radius:12px; border-bottom-right-radius:12px; }}
  .chat-msg.assistant {{ margin-right:auto; background:var(--card); color:var(--text); border:1px solid var(--border); border-top-left-radius:4px; border-top-right-radius:12px; border-bottom-left-radius:12px; border-bottom-right-radius:12px; }}
  .chat-msg.error {{ margin-right:auto; background:var(--down-bg); color:var(--down-text); border-top-left-radius:4px; border-top-right-radius:12px; border-bottom-left-radius:12px; border-bottom-right-radius:12px; }}
  .chat-msg .role {{ font-size:11px; color:var(--muted); margin-bottom:2px; }}
  /* 消息底部元信息 (耗时 · 模型) — 小号灰色, 与正文隔断 */
  .msg-meta {{ font-size:11px; color:var(--muted); margin-top:6px; padding-top:5px; border-top:1px solid var(--border); opacity:.75; white-space:nowrap; }}
  .chat-input-row {{ display:flex; gap:8px; align-items:flex-end; }}
  .chat-input {{ flex:1; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--input-bg); color:var(--text); font-size:14px; resize:vertical; }}
  .chat-send {{ width:44px; height:44px; border-radius:50%; background:#95ec69; color:#fff; font-size:18px; display:flex; align-items:center; justify-content:center; cursor:pointer; border:none; transition:opacity .15s; }}
  .chat-send:hover {{ opacity:.85; }}
  .chat-send:active {{ opacity:.7; }}
  .chat-send svg {{ width:22px; height:22px; }}
  @media (max-width: 480px) {{ .chat-card {{ height:calc(100vh - 100px); }} }}
  /* 模型供应商卡片网格 (参考 9Router providers) */
  .providers-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:12px; }}
  .provider-card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:16px; cursor:pointer; transition:border-color .15s; position:relative; }}
  .provider-card:hover {{ border-color:var(--accent); }}
  .provider-card .p-ico {{ width:40px; height:40px; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:20px; margin-bottom:10px; }}
  .provider-card .p-name {{ font-size:14px; font-weight:600; margin-bottom:4px; }}
  .provider-card .p-status {{ font-size:12px; display:inline-flex; align-items:center; gap:4px; padding:3px 10px; border-radius:20px; margin-top:6px; }}
  .provider-card .p-status.connected {{ background:var(--ok-bg); color:var(--ok-text); }}
  .provider-card .p-status.pending {{ background:var(--down-bg); color:var(--down-text); }}
  .provider-card .p-badge {{ position:absolute; top:10px; right:10px; font-size:11px; padding:2px 8px; border-radius:10px; background:var(--accent); color:#fff; }}
  .provider-card .p-desc {{ font-size:11px; color:var(--muted); margin-top:6px; }}
  /* 卡片内联配置区 (响应式) */
  /* 卡片内联配置区 — 绝对定位覆盖在原卡片容器上, 不改卡片高度 (网格不被撑大) */
  .p-edit {{ position:absolute; top:0; left:0; right:0; bottom:0; z-index:5; background:var(--card); border-radius:12px; padding:12px; display:flex; flex-direction:column; justify-content:center; box-shadow:0 2px 12px var(--shadow); }}
  .p-edit-label {{ font-size:11px; color:var(--muted); margin-bottom:6px; }}
  .p-edit-input {{ width:100%; padding:7px 9px; border:1px solid var(--border); border-radius:8px; background:var(--input-bg); color:var(--text); font-size:13px; box-sizing:border-box; margin-bottom:8px; }}
  .p-edit-btns {{ display:flex; gap:8px; }}
  .p-edit-btns button {{ flex:1; padding:7px 0; border:none; border-radius:8px; font-size:12px; cursor:pointer; }}
  .p-edit-save {{ background:var(--accent); color:#fff; }}
  .p-edit-cancel {{ background:var(--card); color:var(--text); border:1px solid var(--border) !important; }}
  @media (max-width: 600px) {{ .providers-grid {{ grid-template-columns:1fr 1fr; }} }}
  /* 状态网格 — 聚合分散状态 (2列, 4张卡片含内核, 适配小窗口) */
  .status-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px; }}
  .status-card {{ background:var(--card); border-radius:12px; padding:14px 16px; box-shadow:0 1px 4px var(--shadow); }}
  .status-card h3 {{ font-size:13px; margin:0 0 8px; color:var(--muted); display:flex; align-items:center; gap:6px; }}
  .status-card .mini {{ font-size:12px; color:var(--muted); line-height:1.7; }}
  .status-card .mini b {{ color:var(--text); font-weight:500; }}
  .status-card .mini .row {{ padding:2px 0; border:none; font-size:12px; }}
  .status-card .mini .row .val {{ font-size:12px; }}
  /* 移动端网格变单列 */
  @media (max-width: 600px) {{
    .status-grid {{ grid-template-columns:1fr; }}
  }}
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
  <div class="layout">
  <!-- 侧边栏导航 (参考 9Router) -->
  <div class="sidebar" id="sidebar">
    <div class="sidebar-brand">
      <div class="logo">🔧</div>
      <div>
        <div class="name">Hermes Core</div>
        <div class="ver" data-i18n="local-kernel">本地内核</div>
      </div>
    </div>
    <div class="nav-item active" data-nav="chat" onclick="switchNav('chat')">
      <span class="ico">💬</span> <span data-i18n="nav-chat">聊天</span>
    </div>
    <div class="nav-item" data-nav="status" onclick="switchNav('status')">
      <span class="ico">📊</span> <span data-i18n="nav-status">状态</span>
    </div>
    <div class="nav-item" data-nav="config" onclick="switchNav('config')">
      <span class="ico">⚙️</span> <span data-i18n="nav-config">配置</span>
    </div>
    <div class="nav-item" data-nav="messaging" onclick="switchNav('messaging')">
      <span class="ico">📡</span> <span data-i18n="nav-messaging">消息平台</span>
    </div>
    <div class="nav-section" data-i18n="nav-providers">模型供应商</div>
    <div class="nav-item" data-nav="providers" onclick="switchNav('providers')">
      <span class="ico">🍟</span> <span data-i18n="nav-providers-title">供应商</span>
    </div>
  </div>
  <div class="sidebar-overlay" id="sidebar-overlay" onclick="toggleSidebar()"></div>

  <!-- 主内容区 -->
  <div class="main">
  <div class="topbar">
    <div style="display:flex;align-items:center;gap:10px;">
      <button class="hamburger" onclick="toggleSidebar()">☰</button>
    </div>
    <div class="topbar-actions">
      <button class="icon-btn" onclick="toggleLang()" id="btn-lang">🌐 EN</button>
      <button class="icon-btn" onclick="toggleTheme()" id="btn-theme">🌙</button>
    </div>
  </div>

  <!-- 聊天面板 -->
  <div class="nav-panel" id="panel-chat">
  <div class="card chat-card">
    <h2>💬 <span data-i18n="nav-chat">聊天</span></h2>
    <div id="chat-msgs" class="chat-msgs"></div>
    <div class="chat-input-row">
      <textarea id="chat-input" class="chat-input" rows="2" placeholder="" data-i18n="chat-placeholder" enterkeyhint="send"></textarea>
      <button class="chat-send" onclick="sendChat()" aria-label="发送">↑</button>
    </div>
    <p style="font-size:11px;color:var(--muted);margin:6px 0 0;" data-i18n="chat-hint">通过本机 api_server (8642) 对话。发送即触发一次对话。</p>
  </div>
  </div>

  <!-- 状态面板 -->
  <div class="nav-panel" id="panel-status" style="display:none">
  <!-- 聚合状态网格: 内核 / 消息网关 / LLM / Dashboard (2列4卡, 适配小窗口) -->
  <div class="status-grid">
    <div class="status-card">
      <h3>🔧 <span data-i18n="core-status">内核状态</span> <span class="status {STATUS_CLS}">{STATUS_TEXT}</span></h3>
      <div class="mini">
        <div class="row"><span class="label" data-i18n="state">状态</span><span class="val">{STATE}</span></div>
        <div class="row"><span class="label" data-i18n="platform">平台</span><span class="val">{PLATFORM}</span></div>
        <div class="row"><span class="label" data-i18n="version">版本</span><span class="val">{VERSION}</span></div>
        <div class="row"><span class="label" data-i18n="core-port">内核端口</span><span class="val">{CORE_PORT}</span></div>
        <div class="row"><span class="label" data-i18n="api-addr">API 地址</span><span class="val">http://127.0.0.1:{CORE_PORT}</span></div>
      </div>
    </div>
    <div class="status-card">
      <h3>📡 <span data-i18n="gateway">消息网关</span> <span class="status {GW_CLS}">{GW_TEXT}</span></h3>
      <div class="mini">{GW_PLATFORMS_MIN}</div>
    </div>
    <div class="status-card">
      <h3>🧠 <span data-i18n="fallback-llm">默认 LLM</span> <span class="status {LLM_CLS}">{LLM_TEXT}</span></h3>
      <div class="mini">{LLM_ROWS_MIN}</div>
    </div>
    <div class="status-card">
      <h3>📊 <span data-i18n="dashboard">Dashboard</span> <span class="status {DASH_CLS}">{DASH_TEXT}</span></h3>
      <div class="mini">
        <div><b data-i18n="state">状态</b>: {DASH_DETAIL}</div>
        <div><b data-i18n="user">用户</b>: {DASH_USER}</div>
        <div><b data-i18n="port">端口</b>: {DASH_PORT}</div>
      </div>
    </div>
  </div>
  </div>

  <!-- 配置面板 -->
  <div class="nav-panel" id="panel-config" style="display:none">
  <div class="card">
    <h2>⚙️ <span data-i18n="basic-config">基础配置</span></h2>
    <p style="font-size:12px;color:var(--muted);margin:0 0 8px;" data-i18n="config-hint">修改后点击保存，再点"重启内核"生效。敏感项已脱敏显示。</p>
    <div id="msg" class="msg"></div>
    <form id="cfgform">
      {FORM_FIELDS}
    </form>
    <div class="btn-row">
      <button class="primary" onclick="saveConfig('cfgform')" data-i18n="save-config">💾 保存配置</button>
      <button class="warn" onclick="restartCore()" data-i18n="restart">🔄 重启内核</button>
    </div>
    <p style="font-size:12px;color:var(--muted);margin:12px 0 0;line-height:1.5;" data-i18n="restart-hint">
      ℹ️ 重启内核会同时重启 <b>消息网关</b>（Feishu/Telegram/微信等平台连接）与 cron 调度，消息平台短暂断开后自动恢复。
    </p>
  </div>
  </div>

  <!-- 消息平台面板 -->
  <div class="nav-panel" id="panel-messaging" style="display:none">
  <div class="card">
    <h2>📡 <span data-i18n="nav-messaging">消息平台</span></h2>
    <p style="font-size:12px;color:var(--muted);margin:0 0 12px;line-height:1.6;" data-i18n="messaging-hint">配置飞书/微信消息渠道，让 Hermes 能从聊天平台收发消息。保存后点「重启内核」生效。飞书需先在开放平台创建应用；微信 Token 为渠道下发的验证凭据。</p>
    <div id="msg-messaging" class="msg"></div>
    <form id="cfgform-msg">
      {MSG_FIELDS}
    </form>
    <div class="btn-row">
      <button class="primary" onclick="saveConfig('cfgform-msg','msg-messaging')" data-i18n="save-config">💾 保存配置</button>
      <button class="warn" onclick="restartCore()" data-i18n="restart">🔄 重启内核</button>
    </div>
    <div class="wxqr-section">
      <div class="cfg-section-title">📱 微信扫码登录</div>
      <p style="font-size:12px;color:var(--muted);margin:0 0 8px;" data-i18n="wxqr-hint">用微信扫二维码即可自动绑定账号并写入 Token，无需手动填账号 ID/Token。扫码需联网访问微信 iLink。</p>
      <button class="wxqr-btn" onclick="wxQrStart()" data-i18n="wxqr-start">📱 开始扫码登录</button>
      <div id="wxqr-area" style="display:none;margin-top:10px;text-align:center;">
        <img id="wxqr-img" style="width:200px;height:200px;border:1px solid var(--border);border-radius:8px;background:#fff;" alt="微信二维码"/>
        <div id="wxqr-msg" style="font-size:12px;color:var(--muted);margin-top:6px;" data-i18n="wxqr-wait">用微信扫一扫上面的二维码...</div>
        <div><a id="wxqr-link" href="#" target="_blank" style="font-size:11px;color:var(--accent);" data-i18n="wxqr-open">打不开？点这里打开二维码链接</a></div>
      </div>
    </div>
    <p style="font-size:12px;color:var(--muted);margin:12px 0 0;line-height:1.6;" data-i18n="messaging-status">
      {MSG_STATUS}
    </p>
  </div>
  </div>

  <!-- 模型供应商面板 -->
  <div class="nav-panel" id="panel-providers" style="display:none">
  <div class="card">
    <h2>🍟 <span data-i18n="nav-providers-title">供应商</span></h2>
    {DEFAULT_MODEL_HTML}
    <p style="font-size:12px;color:var(--muted);margin:12px 0 12px;" data-i18n="providers-hint">点击供应商卡片配置 API Key。默认模型由安装向导设置，9Router 为本地代理（非强制默认）。</p>
    {PROVIDERS_GRID}
  </div>
  </div>

  <div class="meta">Hermes Core <b>v{STATUS_VER}</b> · 本地内核 · {TS}</div>
  </div>
  </div>

<script>
const HERMES_AUTH = {AUTH_TOKEN};
const LLM_MODEL_NAME = {LLM_MODEL_JSON};
const I18N = {{
  zh: {{
    'nav-chat':'聊天','nav-status':'状态','nav-config':'配置','nav-messaging':'消息平台','nav-providers':'供应商','nav-providers-title':'供应商','local-kernel':'本地内核',
    'chat-placeholder':'输入消息，Enter 发送...','chat-hint':'通过本机 api_server (8642) 对话。发送即触发一次对话。',
    'providers-hint':'点击供应商卡片配置 API Key。默认模型由安装向导设置，9Router 为本地代理（非强制默认）。',
    'messaging-hint':'配置飞书/微信消息渠道，让 Hermes 能从聊天平台收发消息。保存后点「重启内核」生效。飞书需先在开放平台创建应用；微信 Token 为渠道下发的验证凭据。',
    'messaging-status':'📡 状态提示：配置飞书/微信后重启内核，Hermes 消息网关即连接对应平台。当前渠道连接状态见「状态」页的消息网关卡片。',
    'wxqr-hint':'用微信扫二维码即可自动绑定账号并写入 Token，无需手动填账号 ID/Token。扫码需联网访问微信 iLink。',
    'wxqr-start':'📱 开始扫码登录','wxqr-wait':'用微信扫一扫上面的二维码...','wxqr-open':'打不开？点这里打开二维码链接',
    'feishu-hint':'配置飞书消息渠道，保存后重启内核生效。验证 Token 为飞书开放平台下发的验证凭据。',
    'wechat-hint':'配置微信消息渠道，保存后重启内核生效。Token 为微信渠道下发的验证凭据。',
    'core-status':'内核状态','state':'状态','platform':'平台',
    'version':'版本','core-port':'内核端口','api-addr':'API 地址','gateway':'消息网关','fallback-llm':'默认 LLM',
    'dashboard':'Dashboard','user':'用户','port':'端口','basic-config':'基础配置','config-hint':'修改后点击保存，再点"重启内核"生效。敏感项已脱敏显示。',
    'save-config':'💾 保存配置','restart':'🔄 重启内核','restart-hint':'ℹ️ 重启内核会同时重启 消息网关 与 cron 调度',
    'saved':'✅ 配置已保存，请点"重启内核"生效','save-fail':'❌ 保存失败: ','restarting':'🔄 内核正在重启，几秒后刷新页面查看状态','restart-fail':'❌ 重启失败: ',
    'running':'● 运行中','stopped':'● 已停止','healthy':'healthy','unconfigured':'○ 未配置'
  }},
  en: {{
    'nav-chat':'Chat','nav-status':'Status','nav-config':'Config','nav-messaging':'Messaging','nav-providers':'Providers','nav-providers-title':'Providers','local-kernel':'Local Kernel',
    'chat-placeholder':'Type a message, Enter to send...','chat-hint':'Chat via local api_server (8642). Sending triggers one conversation.',
    'providers-hint':'Click a provider card to configure its API Key. Default model is set in install wizard; 9Router is a local proxy (not forced default).',
    'messaging-hint':'Configure Feishu/WeChat messaging channels so Hermes can send/receive messages from chat platforms. Save then Restart Core to apply. Feishu needs an app created on its Open Platform; WeChat Token comes from the channel.',
    'messaging-status':'📡 Tip: after configuring Feishu/WeChat and restarting the core, the Hermes message gateway connects to those platforms. See the Message Gateway card on the Status page for current connection state.',
    'wxqr-hint':'Scan the QR with WeChat to auto-bind your account and write the token — no need to fill Account ID/Token manually. Requires internet access to WeChat iLink.',
    'wxqr-start':'📱 Start QR Login','wxqr-wait':'Scan the QR code above with WeChat...','wxqr-open':'Can\'t open? Click here for the QR link',
    'feishu-hint':'Configure Feishu channel. Save and restart to apply. Verification Token comes from Feishu Open Platform.',
    'wechat-hint':'Configure WeChat channel. Save and restart to apply. Token comes from WeChat channel.',
    'core-status':'Core Status','state':'State','platform':'Platform',
    'version':'Version','core-port':'Core Port','api-addr':'API Address','gateway':'Message Gateway','fallback-llm':'Default LLM',
    'dashboard':'Dashboard','user':'User','port':'Port','basic-config':'Basic Config','config-hint':'Edit then click Save, then Restart Core to apply. Sensitive fields are masked.',
    'save-config':'💾 Save Config','restart':'🔄 Restart Core','restart-hint':'ℹ️ Restarting the core also restarts the message gateway and cron scheduler',
    'saved':'✅ Config saved, click "Restart Core" to apply','save-fail':'❌ Save failed: ','restarting':'🔄 Core restarting, refresh in a few seconds','restart-fail':'❌ Restart failed: ',
    'running':'● Running','stopped':'● Stopped','healthy':'healthy','unconfigured':'○ Not configured'
  }}
}};
// 安全 localStorage (移动端 WebView/隐私模式可能无持久化缓存, 直接访问会抛异常导致整段脚本中断)
function lsGet(k) {{ try {{ return window.localStorage.getItem(k); }} catch (e) {{ return null; }} }}
function lsSet(k, v) {{ try {{ window.localStorage.setItem(k, v); }} catch (e) {{ /* 忽略 */ }} }}
let currentLang = lsGet('hermes_lang') || 'zh';
let currentTheme = lsGet('hermes_theme') || 'light';

function applyI18n() {{
  document.querySelectorAll('[data-i18n]').forEach(el => {{
    const key = el.dataset.i18n;
    const val = I18N[currentLang][key];
    if (!val) return;
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {{ el.placeholder = val; }}
    else {{ el.textContent = val; }}
  }});
  document.getElementById('btn-lang').textContent = currentLang === 'zh' ? '🌐 EN' : '🌐 中文';
  // 更新动态生成的表单 label/状态 (通过 data-i18n 无法覆盖, 用替换文本)
  document.querySelectorAll('label').forEach(l => {{
    // label 文本由后端生成, i18n 主要覆盖静态部分
  }});
}}
function toggleLang() {{
  currentLang = currentLang === 'zh' ? 'en' : 'zh';
  lsSet('hermes_lang', currentLang);
  applyI18n();
}}
function toggleTheme() {{
  currentTheme = currentTheme === 'light' ? 'dark' : 'light';
  lsSet('hermes_theme', currentTheme);
  document.body.dataset.theme = currentTheme;
  document.getElementById('btn-theme').textContent = currentTheme === 'light' ? '🌙' : '☀️';
}}
function switchNav(nav) {{
  // 切换侧边栏菜单
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.nav === nav));
  document.querySelectorAll('.nav-panel').forEach(p => p.style.display = (p.id === 'panel-' + nav) ? 'block' : 'none');
  // 移动端: 切换后收起侧栏
  if (window.innerWidth <= 768) toggleSidebar(false);
}}
function toggleSidebar(open) {{
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebar-overlay');
  const isOpen = open === undefined ? !sidebar.classList.contains('open') : open;
  sidebar.classList.toggle('open', isOpen);
  overlay.classList.toggle('show', isOpen);
}}
const PROVIDER_ENV = {{ '9router':'ROUTER_API_KEY', 'deepseek':'DEEPSEEK_API_KEY', 'mimo':'XIAOMI_API_KEY' }};
const PROVIDER_NAME = {{ '9router':'9Router','deepseek':'DeepSeek','mimo':'Xiaomi MiMo' }};
function editProvider(key) {{
  // 收起其他卡片的展开区
  document.querySelectorAll('.p-edit').forEach(e => e.remove());
  const card = document.querySelector('.provider-card[data-provider="' + key + '"]');
  if (!card) return;
  // 在卡片内插入内联配置区 (响应式)
  const name = PROVIDER_NAME[key] || key;
  const edit = document.createElement('div');
  edit.className = 'p-edit';
  // 用 DOM API 构建, 避免内联 onclick 的引号转义问题
  const label = document.createElement('div');
  label.className = 'p-edit-label';
  label.textContent = name + ' API Key (留空则不改)';
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'p-edit-input';
  input.placeholder = '输入 API Key...';
  input.autocomplete = 'off';
  const btns = document.createElement('div');
  btns.className = 'p-edit-btns';
  const saveBtn = document.createElement('button');
  saveBtn.className = 'p-edit-save';
  saveBtn.textContent = '保存';
  saveBtn.onclick = (e) => {{ e.stopPropagation(); saveProvider(key); }};
  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'p-edit-cancel';
  cancelBtn.textContent = '取消';
  cancelBtn.onclick = (e) => {{ e.stopPropagation(); edit.remove(); }};
  btns.appendChild(saveBtn);
  btns.appendChild(cancelBtn);
  edit.appendChild(label);
  edit.appendChild(input);
  edit.appendChild(btns);
  // 阻止点击编辑区冒泡到卡片 toggle, 避免重新展开导致输入/按钮被重置
  edit.onclick = (e) => e.stopPropagation();
  card.appendChild(edit);
  input.focus();
  input.addEventListener('keydown', (e) => {{ if (e.key === 'Enter' && !e.shiftKey) {{ e.preventDefault(); e.stopPropagation(); saveProvider(key); }} }});
}}
// 点击空白处退出 token 填写状态
document.addEventListener('click', (e) => {{
  if (e.target.closest('.provider-card') || e.target.closest('.p-edit')) return;
  document.querySelectorAll('.p-edit').forEach(el => el.remove());
}});
async function saveProvider(key) {{
  const env = PROVIDER_ENV[key] || '';
  const edit = document.querySelector('.provider-card[data-provider="' + key + '"] .p-edit');
  const input = edit ? edit.querySelector('input') : null;
  const val = input ? input.value.trim() : '';
  const data = {{}};
  data[env] = val;
  const r = await api('/api/config', 'POST', data);
  if (r.ok) {{ setTimeout(() => location.reload(), 600); }}
  else {{ alert('保存失败: ' + (r.error || '')); }}
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
function showMsg(text, isErr, elId) {{
  const el = document.getElementById(elId || 'msg');
  el.textContent = text;
  el.className = 'msg ' + (isErr ? 'err' : 'ok');
}}
async function saveConfig(formId, msgId) {{
  const form = document.getElementById(formId || 'cfgform');
  const fd = new FormData(form);
  // 敏感字段留空 = 不修改 (保留原值)
  const sensitive = ['API_SERVER_KEY', 'ROUTER_API_KEY', 'LLM_API_KEY', 'DASHBOARD_PASSWORD',
                     'FEISHU_APP_SECRET', 'FEISHU_VERIFICATION_TOKEN', 'FEISHU_ENCRYPT_KEY', 'WEIXIN_TOKEN'];
  const data = Object.fromEntries(
    [...fd.entries()].filter(([k, v]) => !(sensitive.includes(k) && !v.trim()))
  );
  const r = await api('/api/config', 'POST', data);
  if (r.ok) showMsg(I18N[currentLang]['saved'], false, msgId);
  else showMsg(I18N[currentLang]['save-fail'] + (r.error || ''), true, msgId);
}}
async function restartCore() {{
  const r = await api('/api/restart', 'POST', {{}});
  if (r.ok) showMsg(I18N[currentLang]['restarting']);
  else showMsg(I18N[currentLang]['restart-fail'] + (r.error || ''), true);
}}
// 微信扫码登录: 获取二维码 → 显示 → 轮询状态 → confirmed 自动写 gateway.env
let wxQrTimer = null;
async function wxQrStart() {{
  const area = document.getElementById('wxqr-area');
  const msgEl = document.getElementById('wxqr-msg');
  if (wxQrTimer) {{ clearInterval(wxQrTimer); wxQrTimer = null; }}
  const r = await api('/api/weixin/qr/start', 'POST', {{}});
  if (!r.ok) {{
    showMsg('❌ ' + (r.error || '二维码获取失败'), true, 'msg-messaging');
    return;
  }}
  area.style.display = 'block';
  const qrUrl = encodeURIComponent(r.qrcode_url || r.qrcode_value);
  // 用在线 QR 渲染服务生成二维码图 (二维码内容是 liteapp URL, 需微信扫)
  document.getElementById('wxqr-img').src = 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=' + qrUrl;
  document.getElementById('wxqr-link').href = r.qrcode_url || r.qrcode_value;
  msgEl.textContent = '用微信扫一扫上面的二维码...';
  // 每 2 秒轮询状态
  wxQrTimer = setInterval(async () => {{
    const s = await api('/api/weixin/qr/status?qrcode=' + encodeURIComponent(r.qrcode_value), 'GET');
    if (s.status === 'confirmed') {{
      clearInterval(wxQrTimer); wxQrTimer = null;
      msgEl.textContent = '✅ 微信已连接！account_id=' + (s.account_id || '');
      showMsg('✅ 微信扫码成功，账号已写入 gateway.env。点「重启内核」生效。', false, 'msg-messaging');
    }} else if (s.status === 'scaned') {{
      msgEl.textContent = '已扫码，请在微信里确认...';
    }} else if (s.status === 'expired') {{
      msgEl.textContent = '二维码已过期，请点「开始扫码登录」刷新';
    }} else if (!s.ok) {{
      msgEl.textContent = '⚠ ' + (s.error || '轮询失败');
    }}
  }}, 2000);
}}
let chatHistory = [];
function addChatMsg(role, text) {{
  const box = document.getElementById('chat-msgs');
  const div = document.createElement('div');
  div.className = 'chat-msg ' + (role === 'user' ? 'user' : (role === 'error' ? 'error' : 'assistant'));
  if (role !== 'user') {{
    const r = document.createElement('div');
    r.className = 'role';
    r.textContent = role === 'assistant' ? 'Hermes' : '错误';
    div.appendChild(r);
  }}
  const body = document.createElement('span');
  body.className = 'msg-body';
  body.textContent = text;
  div.appendChild(body);
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return {{ el: div, body: body, box: box }};
}}
function boxScrollBottom() {{
  const box = document.getElementById('chat-msgs');
  if (box) box.scrollTop = box.scrollHeight;
}}
async function sendChat() {{
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addChatMsg('user', text);
  chatHistory.push({{ role: 'user', content: text }});
  // 显示思考中占位
  const think = addChatMsg('assistant', '⏳ 思考中...');
  const startTime = Date.now();
  const headers = {{ 'Content-Type': 'application/json' }};
  if (HERMES_AUTH) headers['Authorization'] = 'Bearer ' + HERMES_AUTH;
  let replyText = '';
  let modelName = '';
  try {{
    const res = await fetch('/api/chat', {{
      method: 'POST',
      headers,
      body: JSON.stringify({{ messages: chatHistory, stream: true }})
    }});
    if (!res.ok) {{
      const d = await res.json().catch(() => ({{}}));
      throw new Error(d.error || ('HTTP ' + res.status));
    }}
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let curEvent = '';
    while (true) {{
      const {{ done, value }} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {{ stream: true }});
      // 按行解析 SSE
      let idx;
      while ((idx = buf.indexOf('\\n\\n')) !== -1) {{
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const lines = chunk.split('\\n');
        for (const line of lines) {{
          if (line.startsWith('event:')) {{ curEvent = line.slice(6).trim(); continue; }}
          if (line.startsWith('data:')) {{
            const payload = line.slice(5).trim();
            if (payload === '[DONE]') {{ break; }}
            try {{
              const obj = JSON.parse(payload);
              if (curEvent === 'meta') {{ if (obj.model) modelName = obj.model; }}
              else if (obj.text) {{ replyText += obj.text; think.body.textContent = replyText; boxScrollBottom(); }}
            }} catch (e) {{}}
          }}
        }}
        curEvent = '';
      }}
    }}
  }} catch (err) {{
    think.el.className = 'chat-msg error';
    think.body.textContent = '对话失败: ' + err.message;
  }}
  if (replyText) {{
    // 计算耗时 (对齐飞书流式卡片 _format_elapsed: <60s 用 1 位小数, >=60s 用 Xm Ys)
    const ms = Date.now() - startTime;
    const seconds = ms / 1000;
    const dur = seconds < 60 ? (seconds.toFixed(1) + 's') : (Math.floor(seconds / 60) + 'm ' + Math.floor(seconds % 60) + 's');
    think.body.textContent = replyText;
    // 底部元信息: [ 耗时 · 模型 ] — 独立小号元素, 与正文隔断
    const mname = modelName || LLM_MODEL_NAME;
    if (dur) {{
      const metaDiv = document.createElement('div');
      metaDiv.className = 'msg-meta';
      metaDiv.textContent = '[ ' + dur + (mname ? ' · ' + mname : '') + ' ]';
      think.el.appendChild(metaDiv);
    }}
    chatHistory.push({{ role: 'assistant', content: replyText }});
  }}
}}
function toggleDashEnable() {{
  const hid = document.getElementById('dash-enable-val');
  const btn = document.getElementById('dash-enable-btn');
  const txt = document.querySelector('.switch-text');
  const isOn = (hid.value || '').toLowerCase() === 'true';
  const next = isOn ? 'false' : 'true';
  hid.value = next;
  btn.classList.toggle('on', next === 'true');
  txt.textContent = next === 'true' ? '开启' : '关闭';
}}
// 供应商默认 base_url (与后端 MODEL_PROVIDER_URLS 一致)
const DM_URLS = {{ '9router':'http://127.0.0.1:20128/v1', 'deepseek':'https://api.deepseek.com/v1', 'mimo':'https://api.xiaomimimo.com/v1' }};
const DM_DEF_MODEL = {{ '9router':'', 'deepseek':'deepseek-chat', 'mimo':'mimo-v2.5' }};
// 选择供应商时自动带出 Base URL 和默认模型名 (兼容移动端: 不依赖 localStorage)
function dmProviderChanged() {{
  const prov = document.getElementById('dm-provider').value;
  const baseInput = document.getElementById('dm-base');
  const modelInput = document.getElementById('dm-model');
  if (prov === 'custom') {{
    // 自定义: 清空 base, 保留用户已填的模型名
    baseInput.value = '';
    return;
  }}
  if (DM_URLS[prov]) baseInput.value = DM_URLS[prov];
  // 仅在模型名输入框为空时才带出默认模型名
  if (!modelInput.value.trim() && DM_DEF_MODEL[prov]) modelInput.value = DM_DEF_MODEL[prov];
}}
async function saveDefaultModel() {{
  const prov = document.getElementById('dm-provider').value;
  let model = document.getElementById('dm-model').value.trim();
  let base = document.getElementById('dm-base').value.trim();
  if (prov !== 'custom' && !base) base = DM_URLS[prov] || '';
  if (!model && DM_DEF_MODEL[prov]) model = DM_DEF_MODEL[prov];
  const data = {{ LLM_MODEL: model, LLM_BASE_URL: base }};
  const r = await api('/api/config', 'POST', data);
  if (r.ok) showMsg('✅ 默认模型已保存，请点「重启内核」生效');
  else showMsg('❌ 保存失败: ' + (r.error || ''), true);
}}
document.addEventListener('keydown', (e) => {{
  const input = e.target && e.target.id === 'chat-input' ? e.target : null;
  if (input && e.key === 'Enter' && !e.shiftKey) {{ e.preventDefault(); sendChat(); }}
}});
// 初始化
document.body.dataset.theme = currentTheme;
document.getElementById('btn-theme').textContent = currentTheme === 'light' ? '🌙' : '☀️';
applyI18n();
</script>
</body>
</html>
"""


def _render_group_fields(cfg, grp_key):
    """渲染单个分组为独立区块卡片."""
    grp_title, _ = CONFIG_GROUPS.get(grp_key, (grp_key, ""))
    fields_html = []
    # 内核分组: 监听地址 + API 端口 放同一排 (flex row)
    if grp_key == "core":
        row = []
        for key, label, sensitive, grp in CONFIG_FIELDS:
            if grp != grp_key or key in ("API_SERVER_KEY",):
                continue
            val = cfg.get(key, "")
            row.append(
                f'<div class="field-col"><label>{label}</label>'
                f'<input type="text" name="{key}" value="{val}" autocomplete="off"></div>'
            )
        if row:
            fields_html.append('<div class="field-row">' + "".join(row) + "</div>")
    for key, label, sensitive, grp in CONFIG_FIELDS:
        if grp != grp_key:
            continue
        # Dashboard 开关 → 按钮 (switch)
        if key == "DASHBOARD_ENABLED":
            val = cfg.get(key, "false")
            checked = "true" in (val or "").lower()
            fields_html.append(f'<label>{label}</label>')
            fields_html.append(
                f'<input type="hidden" id="dash-enable-val" name="DASHBOARD_ENABLED" value="{val}">'
                f'<div class="switch-wrap">'
                f'<button type="button" id="dash-enable-btn" class="switch{" on" if checked else ""}" '
                f'onclick="toggleDashEnable()"><span class="knob"></span></button>'
                f'<span class="switch-text">{ "开启" if checked else "关闭" }</span></div>'
            )
            continue
        if key == "API_SERVER_KEY":
            shown = _mask(val) if val else "未设置"
            ph = f"当前值: {shown}（留空则不改）"
            fields_html.append(f'<label>{label}</label>')
            fields_html.append(f'<input type="text" name="{key}" placeholder="{ph}" value="" autocomplete="off">')
            continue
        if grp_key == "core":
            continue  # 已在上面 flex row 渲染
        val = cfg.get(key, "")
        if sensitive:
            shown = _mask(val) if val else "未设置"
            ph = f"当前值: {shown}（留空则不改）"
            fields_html.append(f'<label>{label}</label>')
            fields_html.append(f'<input type="text" name="{key}" placeholder="{ph}" value="" autocomplete="off">')
        else:
            fields_html.append(f'<label>{label}</label>')
            fields_html.append(f'<input type="text" name="{key}" value="{val}" autocomplete="off">')
    if not fields_html:
        return ""
    return (f'<div class="cfg-section">'
            f'<div class="cfg-section-title">{grp_title}</div>'
            f'{"".join(fields_html)}'
            f'</div>')


def _form_fields(cfg):
    """配置面板: 内核/Dashboard 分组 (LLM 配置走安装向导+模型供应商页, 不再显示)."""
    parts = []
    for grp_key in ("core", "dash"):
        body = _render_group_fields(cfg, grp_key)
        if body:
            parts.append(body)
    return "\n".join(parts)


def _form_fields_feishu(cfg):
    """飞书面板字段."""
    return _render_group_fields(cfg, "feishu")


def _form_fields_wechat(cfg):
    """微信面板字段."""
    return _render_group_fields(cfg, "wechat")


def _msg_fields(cfg):
    """消息平台面板字段: 飞书 + 微信 两组."""
    parts = []
    for grp_key in ("feishu", "wechat"):
        body = _render_group_fields(cfg, grp_key)
        if body:
            parts.append(body)
    return "\n".join(parts)


def _msg_status(cfg):
    """消息平台连接状态摘要 (配置了哪些字段)."""
    feishu = bool(cfg.get("FEISHU_APP_ID", "") and cfg.get("FEISHU_APP_SECRET", ""))
    wechat = bool(cfg.get("WEIXIN_ACCOUNT_ID", "") and cfg.get("WEIXIN_TOKEN", ""))
    feishu_txt = "🟢 已配置" if feishu else "⚪ 未配置"
    wechat_txt = "🟢 已配置" if wechat else "⚪ 未配置"
    return (f'<div style="display:flex;gap:16px;flex-wrap:wrap;font-size:12px;">'
            f'<span>💬 飞书: <b>{feishu_txt}</b></span>'
            f'<span>💬 微信: <b>{wechat_txt}</b></span></div>')


def _render_default_model(cfg):
    """渲染「默认模型」配置卡片: 显示并允许修改默认模型."""
    model = cfg.get("LLM_MODEL", "")
    base = cfg.get("LLM_BASE_URL", "")
    # 按 base_url 推断当前默认供应商
    prov_name = "未指定"
    base_map = {
        "http://127.0.0.1:20128": "9Router（本机）",
        "api.deepseek.com": "DeepSeek",
        "api.xiaomimimo.com": "Xiaomi MiMo",
    }
    for hint, nm in base_map.items():
        if hint in (base or ""):
            prov_name = nm
            break
    opts = "".join(
        f'<option value="{p["key"]}"{" selected" if prov_name == p["name"] else ""}>{p["name"]}</option>'
        for p in MODEL_PROVIDERS
    )
    opts += '<option value="custom">自定义 URL</option>'
    cur = f'<div class="dm-current"><b>{model or "（未设置）"}</b> @ {base or "（未设置）"} · {prov_name}</div>'
    return (
        '<div class="cfg-section" id="default-model-sec">'
        '<div class="cfg-section-title">🎯 默认模型</div>'
        + cur
        + '<div style="font-size:11px;color:var(--muted);margin:6px 0 10px;">修改默认模型（供应商 / 模型名 / Base URL），保存后重启内核生效。</div>'
        '<div class="field-row">'
        '<div class="field-col"><label>供应商</label>'
        f'<select id="dm-provider" class="dm-input" onchange="dmProviderChanged()">{opts}</select></div>'
        '<div class="field-col"><label>模型名</label>'
        f'<input type="text" id="dm-model" class="dm-input" value="{model}" placeholder="如 deepseek-chat"></div>'
        '<div class="field-col"><label>Base URL</label>'
        f'<input type="text" id="dm-base" class="dm-input" value="{base}" placeholder="如 https://api.example.com/v1"></div>'
        '</div>'
        '<div class="btn-row" style="margin-top:10px;">'
        '<button class="primary" onclick="saveDefaultModel()">💾 保存默认模型</button>'
        '</div>'
        '</div>'
    )


def _render_providers_grid(cfg):
    """渲染模型供应商卡片网格 (参考 9Router providers)."""
    cards = []
    for p in MODEL_PROVIDERS:
        env_val = cfg.get(p["env"], "")
        connected = bool(env_val)
        status = "connected" if connected else "pending"
        status_txt = "● 已连接" if connected else "○ 未配置"
        badge = '<span class="p-badge">默认</span>' if p["default"] else ('<span class="p-badge">本地</span>' if p.get("local") else "")
        ico_bg = p["bg"]
        cards.append(
            f'<div class="provider-card" data-provider="{p["key"]}" onclick="editProvider(\'{p["key"]}\')">'
            f'{badge}'
            f'<div class="p-ico" style="background:{ico_bg};color:#fff;">{p["ico"]}</div>'
            f'<div class="p-name">{p["name"]}</div>'
            f'<span class="p-status {status}">{status_txt}</span>'
            f'<div class="p-desc">{p["desc"]}</div>'
            f'</div>'
        )
    return '<div class="providers-grid">' + "".join(cards) + "</div>"


# ── 微信 QR 扫码登录 (集成 Hermes gateway.platforms.weixin 原生 iLink 机制) ──
# 依赖: 应用 venv 里的 hermes-agent (gateway.platforms.weixin). 不可用则优雅降级.
def _weixin_module():
    """返回 weixin adapter 模块, 不可导入时返回 None."""
    try:
        import sys
        from gateway.platforms import weixin
        return weixin
    except Exception:
        pass
    # 兜底: 尝试把应用 venv 的 site-packages 加入 sys.path 再 import
    try:
        import glob
        for sp in glob.glob("/vol4/@appdata/HermesCore/venv/lib/python*/site-packages"):
            if sp not in sys.path:
                sys.path.insert(0, sp)
        from gateway.platforms import weixin
        return weixin
    except Exception:
        return None


def _weixin_qr_available():
    """是否可用 (依赖 weixin adapter + aiohttp/cryptography)."""
    m = _weixin_module()
    if m is None:
        return False
    try:
        return bool(m.check_weixin_requirements())
    except Exception:
        return False


def _weixin_qr_start(bot_type="3"):
    """获取微信登录二维码. 返回 dict {qrcode_url, qrcode_value} 或错误."""
    m = _weixin_module()
    if m is None:
        return {"error": "微信适配器不可用 (未安装 hermes-agent 或无法导入)"}
    try:
        import asyncio
        async def _fetch():
            import aiohttp
            async with aiohttp.ClientSession(trust_env=True) as session:
                resp = await m._api_get(
                    session,
                    base_url=m.ILINK_BASE_URL,
                    endpoint=f"{m.EP_GET_BOT_QR}?bot_type={bot_type}",
                    timeout_ms=m.QR_TIMEOUT_MS,
                )
                return resp
        resp = asyncio.run(_fetch())
        value = str(resp.get("qrcode") or "")
        url = str(resp.get("qrcode_img_content") or "")
        if not value:
            return {"error": "二维码响应缺少 qrcode"}
        return {"qrcode_url": url or value, "qrcode_value": value}
    except Exception as e:
        return {"error": f"获取二维码失败: {e}"}


def _weixin_qr_poll(qrcode_value):
    """轮询扫码状态. confirmed 时自动写 gateway.env. 返回 dict."""
    m = _weixin_module()
    if m is None:
        return {"error": "微信适配器不可用"}
    try:
        import asyncio
        async def _poll():
            import aiohttp
            async with aiohttp.ClientSession(trust_env=True) as session:
                resp = await m._api_get(
                    session,
                    base_url=m.ILINK_BASE_URL,
                    endpoint=f"{m.EP_GET_QR_STATUS}?qrcode={qrcode_value}",
                    timeout_ms=m.QR_TIMEOUT_MS,
                )
                return resp
        resp = asyncio.run(_poll())
        status = str(resp.get("status") or "wait")
        if status == "confirmed":
            account_id = str(resp.get("ilink_bot_id") or "")
            token = str(resp.get("bot_token") or "")
            base_url = str(resp.get("baseurl") or m.ILINK_BASE_URL)
            user_id = str(resp.get("ilink_user_id") or "")
            if not account_id or not token:
                return {"status": status, "error": "扫码确认但凭据不完整"}
            # 写 gateway.env (WEIXIN_ACCOUNT_ID/TOKEN/BASE_URL/CDN_BASE_URL)
            data = {
                "WEIXIN_ACCOUNT_ID": account_id,
                "WEIXIN_TOKEN": token,
                "WEIXIN_BASE_URL": base_url,
                "WEIXIN_CDN_BASE_URL": "https://novac2c.cdn.weixin.qq.com/c2c",
            }
            _save_config(data)
            return {"status": status, "account_id": account_id}
        return {"status": status}
    except Exception as e:
        return {"error": f"轮询扫码状态失败: {e}"}


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

    def _stream_chat(self, messages):
        """SSE 流式聊天响应."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        gen, err, captured_model = _chat_proxy(messages, stream=True)
        if err:
            self.wfile.write(f"event: error\ndata: {json.dumps({'error': err})}\n\n".encode())
            self.wfile.flush()
            return
        try:
            for piece in gen:
                if piece:
                    self.wfile.write(f"data: {json.dumps({'text': piece})}\n\n".encode())
                    self.wfile.flush()
        except Exception:
            pass
        try:
            # 发送 model 元信息 (前端用于展示 【耗时 · 模型名】)
            mdl = captured_model[0] if captured_model else ""
            self.wfile.write(f"event: meta\ndata: {json.dumps({'model': mdl})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception:
            pass

    def do_GET(self):  # noqa: N802
        if self.path == "/":
            self._render_page()
        elif self.path == "/api/config":
            if not self._check_auth():
                return
            self._json({"ok": True, "config": _load_config()})
        elif self.path.startswith("/api/weixin/qr/status"):
            if not self._check_auth():
                return
            from urllib.parse import urlparse, parse_qs
            q = parse_qs(urlparse(self.path).query).get("qrcode", [""])[0]
            if not q:
                self._json({"ok": False, "error": "缺少 qrcode 参数"})
                return
            result = _weixin_qr_poll(q)
            self._json({"ok": "error" not in result, **result})
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
            allowed = {k for k, _, _, _ in CONFIG_FIELDS}
            clean = {k: (v or "").strip() for k, v in data.items() if k in allowed}
            ok, err = _save_config(clean)
            self._json({"ok": ok, "error": err} if not ok else {"ok": True})
        elif self.path == "/api/weixin/qr/start":
            if not self._check_auth():
                return
            if not _weixin_qr_available():
                self._json({"ok": False, "error": "微信 QR 登录不可用 (需 hermes-agent 的 weixin 适配器)"})
                return
            result = _weixin_qr_start()
            if "error" in result:
                self._json({"ok": False, "error": result["error"]})
            else:
                self._json({"ok": True, **result})
        elif self.path == "/api/restart":
            if not self._check_auth():
                return
            ok, err = _do_restart()
            self._json({"ok": ok, "error": err} if not ok else {"ok": True})
        elif self.path == "/api/chat":
            # 聊天: 代理到本机 api_server (8642) 的 /v1/chat/completions
            if not self._check_auth():
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length).decode()) if length else {}
            except Exception:
                data = {}
            messages = data.get("messages", [])
            want_stream = bool(data.get("stream"))
            if want_stream:
                self._stream_chat(messages)
            else:
                reply, err = _chat_proxy(messages)
                if reply is not None:
                    self._json({"ok": True, "reply": reply})
                else:
                    self._json({"ok": False, "error": err or "chat failed"})
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
        # 紧凑版 (mini 卡片)
        gw_platforms_min = []
        if plats:
            for name, p in plats.items():
                pstate = p.get("state", "?") if isinstance(p, dict) else "?"
                ptext = f'{name}: <b>{pstate}</b>'
                gw_platforms_min.append(f'<div>{ptext}</div>')
        else:
            gw_platforms_min.append('<div style="color:#999">未检测到平台</div>')

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
        # 紧凑版 (mini 卡片)
        llm_rows_min = []
        llm_rows_min.append(f'<div>状态: <b>{llm.get("msg", "")}</b></div>')
        if llm.get("model"):
            llm_rows_min.append(f'<div>模型: <b>{llm["model"]}</b></div>')

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
            GW_PLATFORMS_MIN="\n".join(gw_platforms_min),
            LLM_CLS=llm_cls,
            LLM_TEXT=llm_text,
            LLM_ROWS="\n".join(llm_rows),
            LLM_ROWS_MIN="\n".join(llm_rows_min),
            DASH_CLS=dash_cls,
            DASH_TEXT=dash_text,
            DASH_DETAIL=dash_detail,
            DASH_USER=dash_user,
            DASH_PORT=dash_port,
            FORM_FIELDS=_form_fields(cfg),
            MSG_FIELDS=_msg_fields(cfg),
            MSG_STATUS=_msg_status(cfg),
            PROVIDERS_GRID=_render_providers_grid(cfg),
            DEFAULT_MODEL_HTML=_render_default_model(cfg),
            AUTH_TOKEN=json.dumps(API_KEY),   # 注入鉴权 token 到前端 JS
            LLM_MODEL_JSON=json.dumps(cfg.get("LLM_MODEL", "")),   # 注入默认模型名
            STATUS_VER=STATUS_VER,
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
