# Hermes Core for fnOS

Hermes Agent 本地内核的飞牛 fnOS 应用包 — 独立运行的 Gateway API 服务，供 Hermes WebUI 等前端连接。

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
- **状态页** (`:8648`) — 提供内核健康状态的 HTML 页面，桌面图标/手机 App 打开即见（避免 iframe 加载 JSON API 报错）。

## LLM 模型连接配置（安装向导 / 应用设置页）

支持两种方式，二选一或同时配置：

| 字段 | 说明 |
|------|------|
| `router_api_key` | 9Router API Key（本机 :20128，可选）。填了则用 9Router。 |
| `llm_base_url` | 兜底 LLM Base URL — 任意 OpenAI 兼容 API（9Router / 直连 / 其他代理） |
| `llm_api_key` | 兜底 API Token |
| `llm_model` | 兜底模型名 |

优先级：填了 `llm_base_url` 用兜底（Custom LLM），否则用 9Router。都不填则默认 9Router。

## 开发

```bash
# 在飞牛上
fnpack build   # 生成 HermesCore.fpk
```

## License

MIT
