# AGENTS.md

AI 图片生成平台：用户上传参考图 + 文字，调 OpenAI 生成图片，按积分计费。

## 架构

两套服务，职责分离：

- **国内机器**：`frontend/` (Vue3 SPA) + `backend-cn/` (FastAPI 主后端)。处理注册/登录/JWT、积分扣减退还、图片代理转发；存 MongoDB(用户/积分/任务)。
- **香港机器**：`backend-hk/` (FastAPI 网关，无数据库)。调 OpenAI，图片存 `/storage/{uid}/`，仅接受国内服务调用(内部密钥 + IP 白名单)。

国内 → 香港通过 HTTPS + `X-Internal-Secret` 头通信。

关键约定：
- 用户/积分/任务全存国内 MongoDB；香港只存图片文件。
- 用户不直连香港，图片由 `backend-cn` 代理转发。
- 邮箱+密码登录，无邮件验证。
- 积分**预扣 + 失败退还**：调用前原子预扣，失败自动退回。
- 充值仅占位(提示「即将上线」)，不接真实支付。
- 面向用户的提示一律中文。
- OpenAI key 仅存香港，绝不进国内服务或前端。

## 目录结构

```
backend-cn/app/        国内主后端 (FastAPI + Motor)
  main.py config.py db.py security.py deps.py
  schemas/ (auth.py, image.py)
  services/ (credit_service.py 预扣退还, hk_client.py 调香港)
  routers/ (auth.py, credits.py, images.py)
backend-hk/app/        香港网关 (无数据库)
  main.py(含内部密钥中间件) config.py
  services/ (openai_client.py, storage.py 防路径穿越)
  routers/ (generate.py, images.py)
frontend/src/          Vue3 + TS + Vite + Pinia + Element Plus
  router/ stores/auth.ts api/(client.ts 拦截器) views/ components/
```

## 数据模型 (MongoDB)

- **users**: `_id, email(唯一), password_hash, credits, status`
- **tasks**: `_id, user_id, prompt, status(pending/success/failed), cost, hk_image_path, error_msg, created_at, finished_at`

## API

国内 `backend-cn` (前缀 `/api`)：
- `POST /auth/register` 注册，赠初始积分，返回 JWT
- `POST /auth/login` 登录，返回 JWT
- `GET /auth/me` 当前用户(含积分)
- `GET /credits` 查积分
- `POST /credits/recharge` 占位充值
- `POST /images/generate` 上传图片+文字生成(核心)，预扣积分
- `GET /images/{task_id}` 代理转发香港图片流(鉴权+校验归属)

香港 `backend-hk` (前缀 `/internal`，全需 `X-Internal-Secret`)：
- `POST /generate` 接收 user_id+prompt+图片，调 OpenAI，返回相对路径
- `GET /images/{uid}/{file}` 返回图片文件

## 生成流程 (POST /api/images/generate)

1. JWT 鉴权拿 user_id。
2. 校验图片格式(png/jpg/webp)、大小(≤`MAX_UPLOAD_MB`)、prompt 非空。
3. 原子预扣 `findOneAndUpdate({_id, credits>=cost}, {$inc:{credits:-cost}})`；不足返回 402「积分已用完，请充值后继续使用」。
4. 创建 task(pending)。
5. 调香港 `/internal/generate`：成功→task=success 存路径，返回 `/api/images/{task_id}`；失败/超时→退还积分，task=failed，返回「图片生成失败，已退还积分，请稍后重试」。

## 配置 (各服务 `.env`，复制 `.env.example`)

backend-cn: `MONGO_URI` `MONGO_DB` `JWT_SECRET` `JWT_EXPIRE_MINUTES` `INITIAL_CREDITS`(默认20) `COST_PER_IMAGE`(默认1) `HK_BASE_URL` `HK_INTERNAL_SECRET` `HK_TIMEOUT_SECONDS` `MAX_UPLOAD_MB` `CORS_ORIGINS`

backend-hk: `INTERNAL_SECRET`(须与国内一致) `OPENAI_API_KEY` `OPENAI_IMAGE_MODEL`(gpt-image-1) `OPENAI_IMAGE_SIZE` `STORAGE_DIR`

## 本地运行 (Python 3.11、Node.js、MongoDB)

后端(两个目录同理)：
```
py -3.11 -m venv .venv && .\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # 填写密钥
.\.venv\Scripts\uvicorn app.main:app --port 9000   # hk 用 9000，cn 用 8000
```

前端：
```
npm install
npm run dev      # localhost:5173，已代理 /api 到 127.0.0.1:8000
npm run build    # 产物 dist/(含 vue-tsc 类型检查)
```

## 验证

- 后端：`python -c "import app.main"` 验证导入；启动后访问 `/health`。
- 前端：`npm run build`。

## 约定

- FastAPI + 异步 Motor；积分增减一律用 MongoDB 原子操作防并发超扣。
- 报错文案中文放 `HTTPException.detail`；前端拦截器统一弹窗(401 跳登录，402 跳充值)。
- 香港图片读取必须带内部密钥，禁止公网直接拉图。
- 新增功能(尺寸/套餐/扣分)从 `config.py` 积分参数扩展，不硬编码。

## 聊天会话功能 (Codex Web)

主页为「我的会话」(`/chat`，`ChatView.vue`)，旧「我的产品」入口已下线(路由 `/products*` 重定向到 `/chat`，旧视图文件保留不动)。用户在 Web 端与香港机器上的 Codex 多轮对话，支持文本 + 最多 4 张图片，SSE 流式输出，按消息预扣积分。

技术栈：香港用 `openai-codex` Python SDK（`AsyncCodex`），复用本机 `codex login` 的 ChatGPT 账号会话；每用户独立工作目录 `<STORAGE_DIR>/workspaces/<uid>/`，沙箱 `workspace_write`。

### 新增文件
- `backend-hk/app/services/codex_service.py`：`AsyncCodex` 单例、`start_thread`/`stream_turn`/`archive_thread`（延迟导入 SDK，未装时模块仍可 import）。
- `backend-hk/app/services/workspace.py`：每用户工作区 + uploads 目录。
- `backend-hk/app/routers/chat.py`：SSE 接口（`/internal/chat/sessions`、`/internal/chat/sessions/{tid}/messages`、`DELETE`）。
- `backend-cn/app/schemas/chat.py`、`services/chat_service.py`（CRUD + 会话级并发锁）、`services/hk_chat_client.py`（流式代理香港 SSE）、`routers/chat.py`（`/api/chat/*`）。
- `frontend/src/api/chat.ts`（会话 CRUD + `sendMessageStream` 用 fetch+ReadableStream 解析 SSE，绕过 axios）、`views/ChatView.vue`。

### 数据模型 (MongoDB，新增)
- **chat_sessions**: `_id, user_id, hk_thread_id, title, created_at, updated_at, last_message_at`
- **chat_messages**: `_id, session_id, user_id, role(user/assistant), content, images[{path,filename}], status(success/failed), error_msg, usage, created_at`

CN 为聊天历史唯一来源（不依赖 `thread.read`）。

### API
国内 `backend-cn` (前缀 `/api/chat`)：
- `GET /sessions` 会话列表 ｜ `POST /sessions` 新建(调香港 `thread_start`)
- `GET /sessions/{id}` 会话+历史消息 ｜ `DELETE /sessions/{id}` 删除(落库+香港归档+清工作区)
- `POST /sessions/{id}/messages` 发消息(multipart `text`+≤`MAX_CHAT_IMAGES` 图)，预扣积分，返回 `text/event-stream`：`event: delta/done/error`
- `GET /sessions/{id}/files/{filename}` 会话图片(鉴权+归属)

香港 `backend-hk` (前缀 `/internal/chat`)：`POST /sessions`、`POST /sessions/{tid}/messages`(SSE)、`DELETE /sessions/{tid}`，全需 `X-Internal-Secret`。

### 聊天流程 (POST /api/chat/sessions/{id}/messages)
1. JWT 鉴权 + 校验会话归属。
2. 校验图片格式/大小/数量、`text` 与图片至少一项非空。
3. 会话级并发锁：同一会话上一条还在生成则返 409「上一条消息还在生成中」。
4. 原子预扣 `COST_PER_CHAT`；不足 402。
5. CN 落盘图片 + 存用户消息 → 调香港 SSE 流式 → 逐字转发前端。
6. `done`：存助手消息(success)；`error`/异常：存 failed + 退还积分。

### 配置 (新增)
backend-cn: `COST_PER_CHAT`(默认1，0=免费) `MAX_CHAT_IMAGES`(默认4)
backend-hk: `CODEX_MODEL`(留空用 SDK 默认) `CODEX_REASONING_EFFORT`(默认high)；依赖 `pip install openai-codex`，且须先在本机执行 `codex login`。
