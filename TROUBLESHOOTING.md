# Hermes Core fnOS — 问题排查与踩坑记录

> 记录开发过程中遇到的问题和解决方案，方便后续迭代参考。

---

## 2026-08-03 (第八次迭代)

### 更新 HermesCore 后配置丢失 — install_callback 空向导覆盖

**现象**：应用中心更新 HermesCore（v0.3.0）后，gateway.env 的 ROUTER_API_KEY / LLM_BASE_URL（LongCat 兜底）全被清空。

**根因**：fnOS 更新时也走 `install_callback`，而它**无条件用空向导值覆盖 gateway.env**（`cat >`）。更新时安装向导为空 → 配置全清空。

**修复**（v0.3.1）：install_callback 仅首次安装（gateway.env 不存在）或向导显式传值时写入，更新时向导为空则**保留已有 gateway.env**。

**教训**：fnOS 的 install_callback 在首次安装和更新时都会触发。凡是用 `cat >` 写配置的 install_callback，必须区分首次 vs 更新，避免空向导清空已有配置。

### 集成 Hermes 原生 dashboard（9119）

**做法**：
- cmd/main 启动 gateway 后，`DASHBOARD_ENABLED=true` 时再启动 `hermes dashboard --port 9119 --host 0.0.0.0 --skip-build --no-open`
- config.yaml 追加 `dashboard.basic_auth`（username/password），公开绑定必须有认证
- Basic Auth 登录端点：`POST /auth/password-login`（JSON + `provider=basic`），**不是** /api/login
- 未设 DASHBOARD_PASSWORD 时自动生成随机密码并记录 core.log
- stop() 需一并停 dashboard（DASHBOARD_PID + pkill）

**坑**：config.yaml 无 `dashboard` 段时，仅设 env 变量 Basic Auth 不生效。SSH `nohup ... &` 后台起 dashboard 会挂起 SSH 连接，用 `setsid ... < /dev/null` 分离。

---

## 2026-08-03 (第七次迭代)

### 合并配置入口 — 去掉应用设置页

**背景**：状态页网页配置与 fnOS 应用设置页（wizard/config + config_callback）功能重复，造成冗余。

**决策**（用户偏好）：保留安装向导 + 状态页网页配置，**去掉应用设置页**。

**改动**：
- 删除 `wizard/config`（应用设置页入口）
- `cmd/config_callback` 改为 no-op（保留文件满足 fnOS 9 生命周期脚本要求，但不做事）
- 保留 `wizard/install` + `install_callback`（安装向导首次引导配置到 gateway.env）

**配置链路（最终）**：
- 安装向导 → install_callback → gateway.env
- 状态页网页 → POST /api/config → gateway.env

**注意**：fnOS 要求 9 个 lifecycle 脚本（install/config/upgrade/uninstall × init/callback）都存在，所以 config_callback 不能删文件，只能改 no-op。

---

## 2026-08-03 (第六次迭代)

### 保存配置报 unauthorized (401)

**现象**：状态页点"保存配置"报 `❌ 保存失败: unauthorized`。

**根因**：后端 `POST /api/config` 和 `/api/restart` 用 Bearer API key 鉴权，但**前端 JS 的 `api()` 函数没带 `Authorization` 头** → 401。

**修复**：后端渲染页面时把 API key 注入前端 JS：
```js
const HERMES_AUTH = {AUTH_TOKEN};   // AUTH_TOKEN 由后端 json.dumps(API_KEY) 注入
```
`api()` 函数自动带 `Authorization: Bearer HERMES_AUTH`。

**安全说明**：API key 会出现在页面 HTML 的 JS 里。因状态服务只监听局域网 NAS，可接受。如更严格，可改用 session/cookie 或一次性 token。

**验证**：带鉴权保存 `{"ok": true}`，无鉴权仍 `{"ok": false, "error": "unauthorized"}`。

---

## 2026-08-03 (第五次迭代)

### 桌面图标消失 — ui/config 顶层 key 必须是 .url

**现象**：HermesCore 应用还在跑（内核+状态页正常），但 fnOS 桌面图标完全消失。

**根因**：做窗口版时把 ui/config 顶层 key 从 `.url` 改成了 `.iframe`。**fnOS 桌面图标注册要求 ui/config 顶层 key 为 `.url`**，即使 `type` 是 `"iframe"`。改成 `.iframe` 后 fnOS 不识别入口 → 桌面图标消失。

**对比**（所有图标正常的 fnOS 应用）：9router、metacubexd、strava、HermesWebUI 的 ui/config 顶层 key 都是 `.url`，尽管 9router/metacubexd/strava 的 `type` 也是 `"iframe"`。

**修复**：ui/config 顶层 key 固定为 `.url`，`type` 保持 `"iframe"`（窗口版）。窗口版/新标签页版的区别只在 `type` 字段，顶层 key 始终 `.url`。

```json
{
  ".url": {                     // ← 必须 .url
    "HermesCore.Application": {
      "type": "iframe",          // ← 窗口版 (或 "url" 新标签页)
      "port": "8648",
      "url": "/"
    }
  }
}
```

**教训**：fnOS 应用 ui/config 的顶层 key 永远是 `.url`（图标注册用），入口形态由内部 `type` 字段决定。不要改顶层 key。

---

## 2026-08-03 (第四次迭代)

### 状态页展示消息网关 + 兜底 LLM 状态

**背景**：用户希望状态页能看消息网关（Feishu/Telegram/微信）和兜底 LLM 的连接状态，并确认重启内核会重启消息网关。

**实现**：
- **消息网关**：内核 `/health/detailed` 返回 `gateway_state` + `platforms`（各平台 state）。状态服务读取并展示。
- **兜底 LLM**：读 gateway.env 的 `LLM_BASE_URL`，探测 `<base>/v1/models`（带 key），显示连接正常/失败/未配置 + 可用模型。
- **重启提示**：状态页注明"重启内核会同时重启消息网关与 cron 调度"。

**关键端点**：内核 `hermes gateway run` 承载消息平台 + cron + API server。`/health/detailed` 是查平台状态的可靠端点（返回 gateway_state + platforms dict）。

**注意**：`hermes gateway run` 本身就会启动消息网关（配置了平台后）。"重启内核"即重启整个 gateway（含消息网关）。

---

## 2026-08-03 (第三次迭代)

### 跨用户残留进程无法 kill (Operation not permitted)

**现象**：SSH 用 yangyu 想 kill HermesCore 应用用户（或相反）的进程，报 `Operation not permitted`。

**原因**：fnOS 应用进程以应用用户（如 HermesCore uid）运行，SSH 的 yangyu 用户无跨用户 kill 权限。残留的 hermes gateway / status_server 进程占着端口，SSH 无法清理。

**影响**：
- 手动 `cmd/main restart` 时 stop 杀不掉应用用户进程 → 8642 仍被占 → start 认为"已在运行"跳过状态服务
- 残留状态服务占 8648，新版无法启动（端口冲突）

**对策**：
- 残留进程只能由**应用中心**（以应用用户运行）或 **root** 清理
- 让用户在应用中心"先停止再启动"，能正确清掉残留
- 测试新版时**换不同端口**（如 8649）避免与残留冲突

### 状态页加配置功能设计

为满足"网页配置"，状态服务新增：
- `GET /` 渲染状态 + 配置表单（脱敏显示）
- `POST /api/config` 保存 gateway.env（Bearer API key 鉴权）
- `POST /api/restart` 一键重启内核

**鉴权**：所有配置 API 需 `Authorization: Bearer <API_SERVER_KEY>`，否则 401。
**脱敏**：敏感字段（API key/token）仅显示前后几位。
**重启**：`subprocess.Popen(["bash", cmd_main, "restart"])` 后台执行，不阻塞。

---

## 2026-08-03 (第二次迭代)

### 手机 App 打开内核图标报 iframe 错误 (WebKitErrorDomain code=102)

**现象**：手机 fnOS App 点 Hermes Core 桌面图标，浏览器报 "无法访问此页面，frame load interrupted"（`WebKitErrorDomain code=102`）。

**根因**：应用入口 `app/ui/config` 配置 `type:"url"` 指向 `:8642/health`，该端点返回 **JSON**（无 CORS 头）。手机 fnOS App 用 **WebView iframe** 加载，iframe 无法显示 JSON → frame load interrupted。

**修复**：
- 新增 `cmd/status_server.py` — 极简 HTML 状态页服务（纯 stdlib，监听 :8648），显示内核健康/平台/版本
- `cmd/main` 启动时一并启动状态服务（start_status_server）
- 入口改为指向 `:8648/`（返回 HTML，iframe 可正常显示）
- `stop` 一并停止状态服务

**教训**：fnOS 应用入口若指向 API 端点（JSON），手机 App iframe 会加载中断。**入口应指向真正的 HTML 页面**。

---

## 2026-08-03 (首次迭代)

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
