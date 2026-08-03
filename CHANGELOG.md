# CHANGELOG

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
