# Hermes Core for fnOS

A fnOS app that runs the Hermes Agent kernel locally — an independent Gateway API service for Hermes WebUI and other frontends.

[![Release](https://img.shields.io/github/v/release/techysy/hermes-core-fnos?label=Release&color=blue)](https://github.com/techysy/hermes-core-fnos/releases)
[![Downloads](https://img.shields.io/github/downloads/techysy/hermes-core-fnos/total?label=Downloads&color=green)](https://github.com/techysy/hermes-core-fnos/releases)
[![fnOS](https://img.shields.io/badge/fnOS-1.1.31xx-blue)](https://developer.fnnas.com/docs/guide)
[![Hermes](https://img.shields.io/badge/Hermes-v0.19.0-purple)](https://github.com/NousResearch/hermes-agent)

- [中文 README](./README.md)

---

## ✨ Features

- **Local kernel, no remote server**: Runs [Hermes Agent](https://github.com/NousResearch/hermes-agent) locally on fnOS, exposing an OpenAI-compatible API at `:8642`
- **Built-in status page + config panel**: view status, manage config, test chat in the browser
- **Multiple LLM providers**: 9Router / DeepSeek / MiMo / any OpenAI-compatible API
- **Optional native Dashboard**: Hermes web admin UI

## 🏗️ Architecture

```
fnOS
├── Hermes Core  (:8642)        ← hermes gateway run (local venv)
│   └─ LLM                      ← 9Router / DeepSeek / MiMo / Custom LLM
├── Status Server (:8648)       ← status_server.py (pure stdlib, zero deps)
│   ├─💬 Chat                   ← SSE proxy → :8642
│   ├─ 📊 Status                ← kernel/gateway/LLM/Dashboard state
│   ├─ ⚙️ Config                ← gateway.env management + one-click restart
│   └─ 🍟 Providers             ← 9Router/DeepSeek/MiMo cards + token management
└── Dashboard (:9119)           ← optional Hermes web admin UI
```

Pair with [Hermes WebUI](https://github.com/techysy/hermes-webui-fnos) pointing at `http://127.0.0.1:8642` for a fully self-contained setup.

## 🚀 Quick Install

1. Download `HermesCore.fpk` from [Releases](https://github.com/techysy/hermes-core-fnos/releases)
2. fnOS → **App Center → Manual Install** → select the fpk
3. Configure listen address / port / API key in the install wizard
4. **Start manually** in App Center after install (fnOS does not auto-start)

```bash
# SSH to fnOS to start manually (optional; use App Center normally)
cd /var/apps/HermesCore && bash cmd/main start
curl -sf http://127.0.0.1:8642/health
```

## 📖 Usage

### Status page config

Open the app icon to reach the status page (`:8648`), edit/save config in the "Config" tab, then **restart the kernel** to apply.

- 📑 "Status" and "Config" tabs
- 🌙 dark/light theme · 🌐 CN/EN switching (remembered)
- 📡 gateway status · 🧠 LLM probe · 📊 Dashboard status

### Ports

| Service | Port | Description |
|---------|------|-------------|
| Gateway API | 8642 | OpenAI-compatible API |
| Status Server | 8648 | status page + config + chat proxy |
| Dashboard | 9119 | Hermes web admin UI (optional) |

### Connect external frontends

```bash
# Point Hermes WebUI etc. at the local kernel for a self-contained setup
# Base URL: http://127.0.0.1:8642
```

## ⚙️ Configuration

Two ways: **install wizard** (first install) and **status page** (daily).

### Common settings

| Field | Description |
|-------|-------------|
| `API_SERVER_HOST` | kernel listen address |
| `API_SERVER_PORT` | kernel API port |
| `API_SERVER_KEY` | kernel API key (auth) |
| `ROUTER_API_KEY` | 9Router API key (local :20128, optional) |
| `LLM_BASE_URL` | fallback LLM base URL (any OpenAI-compatible API) |
| `LLM_API_KEY` | fallback API token |
| `LLM_MODEL` | fallback model name |
| `DASHBOARD_ENABLED` | enable Hermes native dashboard (true/false) |
| `DASHBOARD_USER` / `DASHBOARD_PASSWORD` | dashboard login user/password |

> **LLM priority**: set `LLM_BASE_URL` → Custom LLM; otherwise 9Router. Restart kernel after config changes.

### Enable native Dashboard

```
DASHBOARD_ENABLED=true
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=***
```

Restart the kernel and `:9119` starts too. A random password is generated if none is set (logged in `core.log`).

## 🐛 Troubleshooting

Common install/run/config issues and fixes: see [TROUBLESHOOTING.md](./TROUBLESHOOTING.md).

## 🛠️ Build from Source

```bash
# On the fnOS NAS
fnpack build   # produces HermesCore.fpk
```

## License

MIT
