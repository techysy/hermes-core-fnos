# CHANGELOG

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
