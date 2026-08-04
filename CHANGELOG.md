# CHANGELOG

## 0.4.6 (2026-08-05)

> 正式版 — 完整 UI 迭代合体版：恢复微信风格消息会话 + 默认模型配置调教（继承 0.4.4.14-test 完整 UI），并保留 v0.4.6 全部修复（更新后运行旧代码、版本号动态读取、供应商卡片不撑大网格）。替换线上有问题的 0.4.5。

### 新增 / Added
- **微信风格消息会话 UX** — 内置聊天窗口改为微信风格气泡：自己（右侧绿色 #95ec69）/ 对方（左侧白色），气泡圆角适配；发送按钮改为微信风格 `↑`；消息耗时模型小号分隔显示
- **默认模型配置调教卡片** — 模型供应商页新增「🎯 默认模型」卡片，可直接修改默认模型（供应商 / 模型名 / Base URL），保存后重启内核生效；选择供应商时自动带出 Base URL 和默认模型名（兼容移动端，不依赖 localStorage）
- **移动端适配** — 顶部标题取消、触控友好布局（继承 0.4.4.14-test UI 迭代）

### 修复 / Fixed
- **更新后运行旧状态页代码（核心问题）** — cmd/main 定位 status_server.py 不再从运行数据目录 (`/vol4/@appdata/`) 取，杜绝残留旧副本抢占新代码。根因：`/vol4/@appdata/HermesCore/status_server.py` 残留旧副本 + cmd/main 的 `DATA_DIR` 优先行，导致每次更新后运行的都是旧版本
- **状态页底部版本号升级后不变** — 版本号从硬编码改为**动态读取已安装 manifest**，升级后 footer 自动显示当前应用版本（如 `v0.4.6`）

### 优化 / Improved
- **供应商卡片 API Key 配置不再撑大卡片** — 配置区改为绝对定位覆盖在原卡片容器内，网格不被撑高/变形；修复编辑区内保存/取消冒泡重置

## 0.4.5 (2026-08-04)

### 变更 / Changed
- **重建发版** — 同步最新应用代码（状态页、配置面板、README 规范化、动态 PyPI 版本徽章）
- **内核版本说明** — 应用通过 `pip install hermes-agent` 在线安装内核，安装时自动拉取 PyPI 最新版（当前 **v0.19.0**）。上游 Hermes Agent v0.20.0 已在 GitHub 发布（v2026.8.3）但 **PyPI 尚未同步**；待 PyPI 发布 v0.20.0 后，App Center 更新应用即可自动升级内核（`upgrade_callback` 执行 `pip install --upgrade`），无需卸载重装

## 0.4.4 (2026-08-03)

### 变更 / Changed
- **默认模型通用结构** — 默认模型名 (LLM_MODEL) 和 base_url 都为空时，model 段保持通用结构（`model.default: default`），不强制具体模型/地址
- **向导加默认模型 Base URL** — 安装向导默认模型步骤新增 Base URL 字段（默认 LongCat API），与默认模型名一起填

## 0.4.3 (2026-08-03)

### 变更 / Changed
- **默认模型逻辑重做** — 去掉「9Router 为默认模型」假设：
  - 安装向导只保留一个「默认模型名」入口（LLM_MODEL）
  - 供应商预设：9Router 标记为「本地代理」（非强制默认），DeepSeek/Xiaomi MiMo/LongCat 可选配
  - config.yaml model.default = 向导填的默认模型名，各供应商按 key 是否配置加入 custom_providers

## 0.4.2 (2026-08-03)

### 优化 / Improved
- **供应商 API Key 配置改为卡片内联展开** — 点击供应商卡片时，在卡片内展开配置区（标签+输入框+保存/取消），替代浏览器 prompt 弹窗（嵌入式页面更友好），响应式适配

## 0.4.1 (2026-08-03)

### 优化 / Improved
- **消息气泡宽度** — 气泡 max-width 改为 45%（约页面 1/3），内容超宽自动提行，不再横跨整个页面
- **模型供应商图标** — 侧边栏/面板图标 🔌 改为 🍟，菜单名改为「供应商」

## 0.4.0 (2026-08-03)

### 新增 / Added
- **内置聊天窗口** — 新增「聊天」菜单（默认首页），通过本机 api_server (8642) 直接对话（/api/chat 代理），支持多轮上下文

### 移除 / Removed
- **移除飞书/微信消息渠道配置** — 消息渠道面板及侧边栏菜单移除（渠道无法直接交互，改用内置聊天窗口）

## 0.3.9 (2026-08-03)

### 变更 / Changed
- **配置页去掉「LLM 连接」区块** — 配置面板仅保留内核 + Dashboard；LLM 配置改为通过**安装向导**（9Router 本地代理 + 兜底模型）和**模型供应商页**管理

## 0.3.8 (2026-08-03)

### 变更 / Changed
- **配置分区块** — 配置页每个分组改为独立区块卡片（内核/LLM连接/Dashboard 带边框背景标题，视觉明显分隔）
- **模型供应商页（参考 9Router providers）** — 新增"模型供应商"侧边栏菜单：
  - 卡片网格显示供应商（9Router 默认已连接 / DeepSeek / Xiaomi MiMo / LongCat）
  - 点击卡片配置 API Key
  - 默认模型为本机代理 (9Router)，其余预留
- 新增 DEEPSEEK_API_KEY / XIAOMI_API_KEY 配置字段

## 0.3.7 (2026-08-03)

### 变更 / Changed
- **侧边栏导航 UI（参考 9Router）** — 状态页从顶部标签改为左侧边栏导航：
  - 📊 状态 / ⚙️ 配置 / 💬 飞书 / 💬 微信 四个菜单项
  - 桌面端固定侧边栏 + 移动端汉堡菜单收起（overlay 遮罩）
- **飞书/微信独立面板** — 飞书、微信各自独立配置面板（不再混在配置里）

## 0.3.6 (2026-08-03)

### 新增 / Added
- **飞书/微信消息渠道配置** — 配置页新增两个分组：
  - 💬 飞书：App ID / Secret / 验证 Token(验证码) / 加密 Key
  - 💬 微信：账号 ID / Token(验证码)
  - cmd/main 启动时 export 飞书/微信 env 给 hermes gateway，配置后重启生效

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
