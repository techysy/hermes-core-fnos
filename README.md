# Hermes Core for fnOS

Hermes Agent 本地内核的飞牛 fnOS 应用包 — 独立运行的 Gateway API 服务，供 Hermes WebUI 等前端连接。

[![Release](https://img.shields.io/github/v/release/techysy/hermes-core-fnos.svg?label=Latest&color=blue)](https://github.com/techysy/hermes-core-fnos/releases)
[![Downloads](https://img.shields.io/github/downloads/techysy/hermes-core-fnos/total?label=Downloads&color=green)](https://github.com/techysy/hermes-core-fnos/releases)
[![fnOS](https://img.shields.io/badge/fnOS-1.1.31xx-blue)](https://developer.fnnas.com/docs/guide)
[![Hermes Agent](https://img.shields.io/pypi/v/hermes-agent.svg)](https://pypi.org/project/hermes-agent/)

- [English README](./README.en.md)

---

## ✨ 功能亮点

- **本地内核，无需远程服务器**：在飞牛 NAS 上本地运行 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 内核，提供 `:8642` 的 OpenAI 兼容 API
- **自带状态页 + 配置面板**：网页内查看状态、管理配置、测试聊天
- **多 LLM 供应商**：9Router / DeepSeek / MiMo / 任意 OpenAI 兼容 API
- **可选原生 Dashboard**：Hermes Web 管理界面

## 🏗️ 架构

```
fnOS
├── Hermes Core  (:8642)        ← hermes gateway run (本地 venv)
│   └─ LLM 连接                 ← 9Router / DeepSeek / MiMo / Custom LLM
├── Status Server (:8648)       ← status_server.py (纯 stdlib, 零依赖)
│   ├─💬 聊天                  ← 流式 SSE 代理 → :8642
│   ├─ 📊 状态                  ← 内核/消息网关/LLM/Dashboard 状态
│   ├─ ⚙️ 配置                  ← gateway.env 配置管理 + 一键重启
│   └─ 🍟 模型供应商            ← 9Router/DeepSeek/MiMo 卡片 + Token 管理
└── Dashboard (:9119)           ← Hermes 原生 Web 管理界面 (可选, DASHBOARD_ENABLED)
```

配合 [Hermes WebUI](https://github.com/techysy/hermes-webui-fnos) 前端包，改连 `http://127.0.0.1:8642` 即可完全自闭环。

## 🚀 快速安装

1. 从 [Releases](https://github.com/techysy/hermes-core-fnos/releases) 下载 `HermesCore.fpk`
2. 飞牛 NAS → **应用中心 → 手动安装** → 选择 fpk
3. 安装时按向导配置监听地址 / 端口 / API Key
4. 安装完成后在应用中心**手动启动**（fnOS 不会自动启动）

```bash
# SSH 到飞牛手动启动（可选，正常用应用中心启停）
cd /var/apps/HermesCore && bash cmd/main start
curl -sf http://127.0.0.1:8642/health
```

## 📖 使用说明

### 状态页配置

安装后打开内核图标进入状态页（`:8648`），在「配置」标签编辑保存基础配置，保存后**一键重启内核生效**。

- 📑 「状态」「配置」两个标签页
- 🌙 日夜主题 · 🌐 中英文切换（自动记住）
- 📡 消息网关状态 · 🧠 兜底 LLM 探测 · 📊 Dashboard 状态

### 端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Gateway API | 8642 | OpenAI 兼容 API |
| Status Server | 8648 | 状态页 + 配置 + 聊天代理 |
| Dashboard | 9119 | Hermes Web 管理界面（可选） |

### 连接外部前端

```bash
# Hermes WebUI 等前端指向本地内核即可自闭环
# Base URL: http://127.0.0.1:8642
```

## ⚙️ 配置

**安装向导**（首次安装）与 **状态页网页**（日常调整）两种方式。

### 常用配置项

| 字段 | 说明 |
|------|------|
| `API_SERVER_HOST` | 内核监听地址 |
| `API_SERVER_PORT` | 内核 API 端口 |
| `API_SERVER_KEY` | 内核 API Key（鉴权用） |
| `ROUTER_API_KEY` | 9Router API Key（本机 :20128，可选） |
| `LLM_BASE_URL` | 兜底 LLM Base URL（任意 OpenAI 兼容 API） |
| `LLM_API_KEY` | 兜底 API Token |
| `LLM_MODEL` | 兜底模型名 |
| `DASHBOARD_ENABLED` | 是否启用 Hermes 原生 dashboard（true/false） |
| `DASHBOARD_USER` / `DASHBOARD_PASSWORD` | dashboard 登录用户名/密码 |

> **LLM 优先级**：填了 `LLM_BASE_URL` 用 Custom LLM，否则用 9Router。配置变更后重启内核生效。

### 启用原生 Dashboard

```
DASHBOARD_ENABLED=true
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=***
```

重启内核后 `:9119` 同时启动。未设密码时自动生成随机密码（记录在 `core.log`）。

## 🐛 问题排查

安装/运行/配置的常见问题与修复，见 [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)。

## 🛠️ 从源码构建

```bash
# 在飞牛上
fnpack build   # 生成 HermesCore.fpk
```

## License

MIT
