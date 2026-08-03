# CHANGELOG

## 0.3.5 (2026-08-03)

### 变更 / Changed
- **状态页小窗口适配** — 内核状态改为紧凑卡片，4 张状态卡（内核/网关/LLM/Dashboard）2×2 网格排列，适配 fnOS 桌面最小窗口（内核状态不再占大位置）

## 0.3.4 (2026-08-03)

### 变更 / Changed
- **状态页 UI 优化**：
  - 状态聚合：消息网关/兜底LLM/Dashboard 改为 3 列网格平铺（不再分散堆叠）
  - 配置分组：基础配置按 🔧内核 / 🧠LLM连接 / 📊Dashboard 分组展示

## 0.3.3 (2026-08-03)

### 变更 / Changed
- **前端改造成标签页** — 状态页分「状态」（内核/消息网关/兜底LLM/Dashboard）+「配置」两个标签页
- **日夜主题切换** — 状态页支持深色/浅色主题（CSS 变量 + localStorage 持久化，右上角 🌙/☀️ 按钮）
- **i18n 国际化** — 支持中文/英文切换（右上角 🌐 按钮，localStorage 持久化）
- **Dashboard 状态展示** — 状态页显示 dashboard 运行状态/用户名/端口

### 修复 / Fixed
- 状态页模板花括号转义修复（CSS 变量 + JS 函数用 `{{ }}`，避免 `.format()` 报 KeyError）

## 0.3.2 (2026-08-03)

### 新增 / Added
- **Hermes 原生 dashboard 集成** — HermesCore 启动时同时启动 dashboard（9119），供三方软件/Web 管理连接
  - config.yaml 自动生成 `dashboard.basic_auth`（用户名/密码）
  - gateway.env 新增 `DASHBOARD_ENABLED` / `DASHBOARD_USER` / `DASHBOARD_PASSWORD`
  - 状态页显示 dashboard 状态（运行/未启用）+ 支持网页配置
  - 登录端点：`POST /auth/password-login`（JSON: provider=basic, username, password）
  - 未设密码时自动生成随机密码（记录在 core.log）

## 0.3.1 (2026-08-03)

### 修复 / Fixed
- **更新时配置不再被清空** — install_callback 不再无条件覆盖 gateway.env。仅在首次安装（gateway.env 不存在）或向导显式传值时写入，更新时向导为空则保留已有配置（修复更新 HermesCore 后 ROUTER_API_KEY/兜底 LLM 丢失）

## 0.3.0 (2026-08-03)

### 修复 / Fixed
- **配置保存不再误清空** — 状态页 `POST /api/config` 只更新提交的字段，未提交字段保留原值（之前保存时未填的字段会被清空，如兜底 LLM）
- **保留 platforms 段** — cmd/main 重新生成 config.yaml 时保留已有 `platforms:` 段（飞书/Telegram/微信等消息网关配置），不再因重启覆盖丢失

### 说明 / Docs
- 兜底 LLM 逻辑：填了 `LLM_BASE_URL` 用 Custom LLM（任意 OpenAI 兼容 API），否则用 9Router。详见 README。

## 0.2.9 (2026-08-03)

### 修复 / Fixed
- **config.yaml 每次启动重新生成** — 修复修改 gateway.env（如兜底 LLM / 9Router key）后重启不生效的问题。原先只有 config.yaml 不存在时才生成，导致配置更新无法传播。

### 说明 / Docs
- 兜底 LLM 逻辑：填了 `LLM_BASE_URL` 用 Custom LLM（任意 OpenAI 兼容 API），否则用 9Router。详见 README。

## 0.2.8 (2026-08-03)

### 变更 / Changed
- **合并配置入口** — 移除 fnOS 应用设置页（wizard/config + config_callback 改 no-op），统一配置走安装向导 + 状态页网页，消除重复配置

## 0.2.7 (2026-08-03)

### 修复 / Fixed
- **保存配置报 unauthorized** — 前端 JS 未带鉴权 token，后端 Bearer 鉴权返回 401。现在前端自动注入 API key 作为 Bearer 头。

## 0.2.6 (2026-08-03)

### 变更 / Changed
- **移动端响应式优化** — 状态页适配手机：
  - @media 480px 媒体查询，缩小卡片/间距
  - 输入框字体 ≥16px（防 iOS 自动缩放）
  - 按钮全宽、触控友好（保存/重启竖排）
  - 长文本（API 地址等）自动换行
  - 非敏感字段预填当前值，手机直接改
  - 敏感字段留空=不修改（保留原值）

## 0.2.5 (2026-08-03)

### 修复 / Fixed
- **桌面图标消失** — ui/config 顶层 key 从 `.iframe` 改回 `.url`（fnOS 图标注册要求 `.url` 顶层 key，即使 type 是 iframe）。保持窗口版 type: "iframe"。

## 0.2.4 (2026-08-03)

### 新增 / Added
- **消息网关状态展示** — 状态页显示 gateway 运行状态 + 各平台（Feishu/Telegram/微信/api_server）在线状态
- **兜底 LLM 状态展示** — 状态页探测兜底 LLM API 连接，显示连接正常/失败/未配置 + 可用模型
- 重启说明提示 — 明确"重启内核会同时重启消息网关与 cron 调度"

## 0.2.3 (2026-08-03)

### 新增 / Added
- **状态页支持基础配置** — 网页内可直接编辑并保存内核配置（监听地址/端口/API key/9Router/LLM 连接），保存后点"重启内核"生效
- **鉴权保护** — 配置查看/修改需 Bearer API key（防未授权访问）
- **重启接口** — 页面一键重启内核，配置变更即生效

## 0.2.2 (2026-08-03)

### 变更 / Changed
- **入口改为 iframe 窗口版** — 状态页为纯 HTML 无跨域请求，可在 fnOS 桌面窗口内嵌显示（避免跳新标签页）

## 0.2.1 (2026-08-03)

### 修复 / Fixed
- status_server.py 路径改用 BASH_SOURCE[0] 定位，修复 fnOS 1.1.31xx 下 APP_DIR 差异导致状态页不启动

## 0.2.0 (2026-08-03)

### 新增 / Added
- **状态页服务** (`cmd/status_server.py`) — 极简 HTML 状态页 (:8648)，修复手机 App 打开图标报 iframe 错误 (WebKitErrorDomain code=102)
- 入口改为指向 `:8648/` 状态页，显示内核健康/平台/版本

### 修复 / Fixed
- 手机 fnOS App 用 WebView iframe 打开内核图标时，因入口指向 JSON API (`/health`) 且无 CORS 头导致加载中断

## 0.1.0 (2026-08-03)

### 新增 / Added
- 初始版本 — Hermes Agent 本地内核 fnOS 应用包
- `cmd/main` — 启动/停止/状态管理 hermes gateway run（生命周期实测通过）
- `install_callback` — 建 venv + pip install hermes-agent（联网装，直连失败回退代理）
- 支持离线预打包 venv (`app/venv.tar.gz`)，秒装免联网
- `HERMES_HOME` 指向 `/vol4/@appdata/HermesCore/hermes_home`，不依赖系统 HOME
- **LLM 连接双通道**：
  - 9Router 专用 (`router_api_key`，本机 :20128)
  - 通用兜底 (`llm_base_url` + `llm_api_key` + `llm_model`，任意 OpenAI 兼容 API)
  - 优先级：填了 `llm_base_url` 用兜底，否则 9Router
- 安装向导 (`wizard/install`) + 应用设置页 (`wizard/config`) 配置 LLM 连接
- 纯后台服务，应用中心启停
