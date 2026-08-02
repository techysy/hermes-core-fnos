# Hermes Core fnOS — 问题排查与踩坑记录

> 记录开发过程中遇到的问题和解决方案，方便后续迭代参考。

---

## 2026-08-03

### fnpack build 失败："mkdir /tmp/fnpack.*/app/ui: permission denied"

**现象**：`fnpack build` 报错，源目录复制到临时目录 `/tmp/fnpack.<ts>/` 时 `app/ui` 创建失败。

**根因**：源码目录 `app/` 的权限被破坏成 `d---------`（700，无读执行位）。fnpack 用保留权限复制，复制出的 `app` 也是 700，导致内部 `mkdir app/ui` 无法执行。

**修复**：打包前规范化权限——目录 755、文件 644、可执行脚本 755：

```bash
find . -type d -exec chmod 755 {} \;
find . -type f -exec chmod 644 {} \;
chmod 755 cmd/* wizard/*
```

**教训**：任何 tar/scp/cp 传输都可能改变权限，**build 前务必检查** `ls -ld app app/ui` 为 `drwxr-xr-x`。

---

### fnOS 应用中心以受限用户跑 cmd/main

**现象**：手动 SSH 测试 `cmd/main start` 正常，但应用中心启用后失败。

**实证**（strava 应用诊断日志）：
```
USER=strava UID=969   # fnOS 用受限用户跑 cmd/main
TRIM_APPDEST=/vol4/@appcenter/strava
TRIM_PKGVAR=/vol4/@appdata/strava
PWD=/
```

**关键结论**：
- fnOS 应用用户是 `nologin`（如 `HermesCore`、`strava`），无交互 shell
- 应用用户能建 venv + pip install + 绑定 TCP 端口（strava/metacubexd/9router 均已验证）
- 应用用户能写自己的 `/vol4/@appdata/<App>/`
- **必须显式 `HERMES_HOME=/vol4/@appdata/<App>/hermes_home`**，不能依赖 `$HOME`（nologin 用户可能无 home 目录）

---

### 本地内核 API Server 需要 aiohttp

**现象**：`hermes gateway run` 启动后 `8642` 端口不监听。

**日志**：
```
WARNING gateway.run: API Server: aiohttp not installed
WARNING gateway.run: No adapter available for api_server
```

**修复**：`pip install aiohttp`（api_server 平台必需）。

---

### venv 装 hermes-agent 需联网 1-2 分钟

**现象**：`pip install hermes-agent` 下载 50+ 依赖（~100MB+），需要 1-2 分钟。SSH 60s 超时会中断，`--quiet` 会吞掉错误难排查。

**对策**：
- 在线模式：install_callback 里联网装，需确保不被 fnOS 超时杀掉
- **离线模式（B 方案）**：预打包 venv (`app/venv.tar.gz`)，秒装免联网
- 排障时用非 `--quiet` 手动跑，看真实错误

---

### hermes config.yaml 需完整 custom_providers

**现象**：chat 报 `Unknown provider '9router proxy'`。

**根因**：内核 config.yaml 只有 `model.default`，没有定义 provider 的 `custom_providers`，内核不知道 provider 怎么连。

**修复**：config.yaml 必须包含完整 `custom_providers`（含 base_url + api_key + models）。

---

### 9Router API Key 需要用户配置

**现象**：内核连本机 9Router (:20128) 报 `HTTP 401: Invalid API key`。

**说明**：
- 9Router 的 `/v1/models` 不需要 key，但 `/v1/chat/completions` **需要 API key 鉴权**（requireApiKey）
- 数据库里 key 被脱敏存储（`sk-97a...d585`），无法恢复完整 key
- **必须由用户在安装向导/应用设置页配置** `router_api_key`

---

### LLM 连接双通道设计

为兼容"不一定用 9Router 也可能直连"，提供两套配置：

| 方式 | 字段 |
|------|------|
| 9Router 专用 | `router_api_key` |
| 通用兜底（任意 OpenAI 兼容 API） | `llm_base_url` + `llm_api_key` + `llm_model` |

**优先级**：填了 `llm_base_url` 用兜底（Custom LLM），否则用 9Router。都不填则默认 9Router。

---

### wizard 字段前缀映射

- `wizard/install`（安装向导）：字段以 `wizard_` 前缀传给 **install_callback**（如 `wizard_router_api_key`）
- `wizard/config`（应用设置页）：字段以**裸名**传给 **config_callback**（如 `router_api_key`）
- **install_callback 负责保存安装向导配置**，**config_callback 负责保存应用设置页配置**

---

## 通用排查流程

1. 检查端口：`ss -tlnp | grep <port>`
2. 检查 fnOS 生命周期日志：`cat /var/log/apps/<App>.log`
3. 检查应用日志：`cat /vol4/@appdata/<App>/core.log`
4. 检查诊断日志（cmd/main 无条件记录）：`cat /vol4/@appdata/<App>/core-diag.log`
5. 检查内核配置：`cat /vol4/@appdata/<App>/hermes_home/config.yaml`
6. 健康检查：`curl -sf http://127.0.0.1:<port>/health`
7. 对比工作版本：解压旧 fpk 对比 manifest、config、cmd/ 文件
