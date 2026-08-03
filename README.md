# Hermes Core for fnOS

Hermes Agent 本地内核的飞牛 fnOS 应用包 — 独立运行的 Gateway API 服务，供 Hermes WebUI 等前端连接。

![Release](https://img.shields.io/github/v/release/techysy/hermes-core-fnos?label=Release&color=blue)
![Downloads](https://img.shields.io/github/downloads/techysy/hermes-core-fnos/total?label=Downloads&color=green)
![fnOS](https://img.shields.io/badge/fnOS-1.1.31xx-blue)
![Hermes](https://img.shields.io/badge/Hermes-v0.19.0-purple)

## 是什么

在飞牛 NAS 上本地运行 [Hermes Agent](https://github.com/NousResearch/hermes-agent) 内核（Gateway API），
**不依赖任何远程服务器**。提供 `:8642` 的 OpenAI 兼容 API 端点。

## 架构

```
fnOS
┌────────────────────────────────┐
│ Hermes Core  (:8642)           │
│   └─ hermes gateway run        │
│       └─ 本地 venv hermes-agent │
│           └─ LLM (9Router/MiMo) │
└────────────────────────────────┘
```

配合 [Hermes WebUI](https://github.com/techysy/hermes-webui-fnos) 前端包，改连 `http://127.0.0.1:8642` 即可完全自闭环。

## 安装

1. 从 [Releases](https://github.com/techysy/hermes-core-fnos/releases) 下载 `HermesCore.fpk`
2. 飞牛 NAS → 应用中心 → 手动安装 → 选择 fpk
3. 安装时按向导配置监听地址 / 端口 / API Key
4. 安装完成后在应用中心**手动启动**（fnOS 不会自动启动）

```bash
# SSH 到飞牛手动启动（可选，正常用应用中心启停）
cd /var/apps/HermesCore && bash cmd/main start
curl -sf http://127.0.0.1:8642/health
```

## 说明

- 内核安装在应用数据目录的 venv（`/vol4/@appdata/HermesCore/venv`），首次安装需联网 `pip install hermes-agent`（约 1-2 分钟）。
- `HERMES_HOME` 指向 `/vol4/@appdata/HermesCore/hermes_home`，不依赖系统用户 HOME。
- **状态页 + 配置** (`:8648`) — 网页内查看内核/消息网关/兜底 LLM/Dashboard 状态，并可编辑保存基础配置（监听地址/端口/API key/9Router/LLM/Dashboard 连接），保存后一键重启生效。iframe 窗口版，fnOS 桌面窗口内直接操作。
  - 📡 消息网关：显示 gateway 运行状态 + 各平台（Feishu/Telegram/微信/api_server）在线状态
  - 🧠 兜底 LLM：探测 LLM API 连接，显示连接正常/失败/未配置 + 可用模型
  - 📊 Dashboard：显示 Hermes 原生 dashboard 运行状态 + 用户名 + 端口

## 配置

**安装向导**（首次安装引导）与 **状态页网页**（日常调整）两种方式。网页配置最直观：打开内核图标 → "基础配置"表单 → 保存 → 重启内核生效。

支持配置项：

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
| `DASHBOARD_USER` | dashboard 登录用户名 |
| `DASHBOARD_PASSWORD` | dashboard 登录密码 |

优先级：填了 `llm_base_url` 用兜底（Custom LLM），否则用 9Router。都不填则默认 9Router。

## LLM 模型连接配置（安装向导 / 状态页网页）

支持两种方式，二选一或同时配置：

| 字段 | 说明 |
|------|------|
| `router_api_key` | 9Router API Key（本机 :20128，可选）。填了则用 9Router。 |
| `llm_base_url` | 兜底 LLM Base URL — 任意 OpenAI 兼容 API（9Router / 直连 / 其他代理） |
| `llm_api_key` | 兜底 API Token |
| `llm_model` | 兜底模型名 |

优先级：填了 `llm_base_url` 用兜底（Custom LLM），否则用 9Router。都不填则默认 9Router。

## Hermes 原生 Dashboard

HermesCore 可同时启动 Hermes 原生 Web 管理界面（dashboard，端口 **9119**），便于三方软件/浏览器管理连接。

### 启用

在状态页"基础配置"或 gateway.env 配置：
```
DASHBOARD_ENABLED=true
DASHBOARD_USER=admin
DASHBOARD_PASSWORD=***
```
重启内核后，`8642`（Gateway API）与 `9119`（dashboard）同时启动。未设密码时自动生成随机密码（记录在 `core.log`）。

### 三方软件连接

Dashboard 用 Basic Auth 认证，登录端点 `POST /auth/password-login`：

```bash
# 1. 登录拿 session cookie (JSON, 必须带 provider=basic)
curl -c cookie.txt -X POST http://<NAS>:9119/auth/password-login \
  -H 'Content-Type: application/json' \
  -d '{"provider":"basic","username":"admin","password":"***"}'
# → {"ok":true,"next":"/"}

# 2. 带 cookie 访问 dashboard API
curl -b cookie.txt http://<NAS>:9119/api/sessions
```

### 端口

| 服务 | 端口 | 说明 |
|------|------|------|
| Gateway API | 8642 | OpenAI 兼容 API |
| Dashboard | 9119 | Hermes Web 管理界面 |

## 兜底 LLM 逻辑

内核默认模型选择逻辑（config.yaml 的 `model.default`）：

```
gateway.env 里 LLM_BASE_URL 填了吗？
        │
        ├─ 填了 → 默认用 Custom LLM (兜底)
        │          base_url = LLM_BASE_URL
        │          model    = LLM_MODEL (如 LongCat-2.0)
        │          token    = LLM_API_KEY
        │
        └─ 没填 → 默认用 9Router Proxy (本机 :20128)
                   model = cbcn/deepseek-v4-flash
                   key   = ROUTER_API_KEY
```

- **`9Router Proxy`** 和 **`Custom LLM`** 两个 provider 始终同时写入 `config.yaml` 的 `custom_providers`，**都可用**，只是 `model.default` 决定默认走哪个。
- 兜底是"**默认模型选择**"，不是故障转移（failover）。要切换默认 LLM，改 `LLM_BASE_URL`/`LLM_MODEL` 或清空它回到 9Router，然后重启内核生效。
- 配置变更后**重启内核**生效（状态页"重启内核"按钮或应用中心重启）。

**示例**：配 LongCat 作为兜底
```
LLM_BASE_URL="https://api.longcat.chat/openai"
LLM_API_KEY="***"
LLM_MODEL="LongCat-2.0"
```
重启后 `model.default = Custom LLM / LongCat-2.0`，chat 默认走 LongCat。

## 开发

```bash
# 在飞牛上
fnpack build   # 生成 HermesCore.fpk
```

## License

MIT
