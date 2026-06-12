# AGENTS.md

AI 图片生成平台。用户上传参考图 + 说明文字，调用 OpenAI 生成图片，按积分计费。

## 架构

两套独立服务，职责分离：

```
[用户浏览器]
     │ HTTPS
     ▼
┌─────────────────────────────┐         ┌──────────────────────────┐
│  国内机器 (中国大陆)          │  HTTPS  │  香港机器                  │
│  frontend/  Vue3 SPA        │  +内部  │  backend-hk/ FastAPI 网关 │
│  backend-cn/ FastAPI 主后端 │  密钥   │   - 调用 OpenAI           │
│   - 注册/登录/JWT            │ ──────► │   - 图片存 /storage/{uid}/ │
│   - 积分扣减/退还            │ ◄────── │   - 仅接受国内服务调用     │
│   - 图片代理转发            │         │   - 无数据库(纯文件)       │
│   - MongoDB(用户/积分/任务) │         │                          │
└─────────────────────────────┘         └──────────────────────────┘
```

关键约定：
- 用户、积分、任务数据全部存国内 MongoDB；香港只存图片文件，无数据库。
- 国内用户不直连香港图片 URL，全部由国内 `backend-cn` 代理转发。
- 邮箱 + 密码登录，暂不做邮件验证。
- 积分**预扣 + 失败退还**：调用前原子预扣，生成失败自动退回。
- 充值仅占位（提示「即将上线」），不接真实支付。
- 所有面向用户的提示消息使用中文。
- 香港服务只暴露给国内服务出口 IP（部署时用防火墙/安全组限制）。

## 目录结构

```
aiprovider/
  backend-cn/        国内主后端 (FastAPI + MongoDB)
    app/
      main.py        入口、CORS、生命周期
      config.py      pydantic-settings 读环境变量(含积分参数)
      db.py          Motor 异步连接 + 索引
      security.py    bcrypt 密码 + JWT 签发/校验
      deps.py        get_current_user 鉴权依赖
      schemas/       请求/响应模型 (auth.py, image.py)
      services/
        credit_service.py  原子预扣/退还/任务记录
        hk_client.py       httpx 调香港服务(带内部密钥)
      routers/       auth.py, credits.py, images.py
    requirements.txt
    .env.example
  backend-hk/        香港 AI 网关 (FastAPI, 无数据库)
    app/
      main.py        入口 + 内部密钥校验中间件
      config.py
      services/
        openai_client.py   调 OpenAI images.edit
        storage.py         保存/读取 /storage/{uid}/{uuid}.png(防路径穿越)
      routers/       generate.py, images.py
    requirements.txt
    .env.example
  frontend/          Vue3 + TS + Vite + Pinia + Element Plus
    src/
      main.ts, App.vue
      router/index.ts      路由 + 登录守卫
      stores/auth.ts       token / 用户 / 积分
      api/                 client.ts(axios 拦截器) + auth.ts + images.ts
      views/               LoginView / RegisterView / GenerateView / RechargeView
      components/          AppHeader.vue(含积分展示)
    package.json
    vite.config.ts
```

## 数据模型 (MongoDB, backend-cn)

**users**: `_id, email(唯一索引), password_hash, credits, status`

**tasks**: `_id, user_id, prompt, status(pending/success/failed), cost, hk_image_path, error_msg, created_at, finished_at`

## API

国内 `backend-cn` (前缀 `/api`)：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 邮箱+密码注册，赠送初始积分，返回 JWT |
| POST | `/api/auth/login` | 登录，返回 JWT |
| GET | `/api/auth/me` | 当前用户(含积分) |
| GET | `/api/credits` | 查询积分 |
| POST | `/api/credits/recharge` | 占位充值接口 |
| POST | `/api/images/generate` | 上传图片+文字生成(核心)，预扣积分 |
| GET | `/api/images/{task_id}` | 代理转发香港图片流(需鉴权+校验归属) |

香港 `backend-hk` (前缀 `/internal`，所有请求需 `X-Internal-Secret` 头)：

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/internal/generate` | 接收 user_id+prompt+图片，调 OpenAI，返回相对路径 |
| GET | `/internal/images/{uid}/{file}` | 返回图片文件 |

## 生成流程 (POST /api/images/generate)

1. JWT 鉴权拿到 user_id。
2. 校验图片格式(png/jpg/webp)、大小(≤`MAX_UPLOAD_MB`)、prompt 非空。
3. 原子预扣积分 `findOneAndUpdate({_id, credits>=cost}, {$inc:{credits:-cost}})`；不足返回 402 + 「积分已用完，请充值后继续使用」。
4. 创建 task(pending)。
5. 调香港 `/internal/generate`：
   - 成功 → task=success，存 `hk_image_path`，返回 `/api/images/{task_id}`。
   - 失败/超时 → 退还积分，task=failed，返回「图片生成失败，已退还积分，请稍后重试」。

## 配置 (环境变量)

复制各服务的 `.env.example` 为 `.env` 填写。积分参数全部可配。

backend-cn 关键项：
- `MONGO_URI`, `MONGO_DB`
- `JWT_SECRET`, `JWT_EXPIRE_MINUTES`
- `INITIAL_CREDITS`(注册赠送，默认 20), `COST_PER_IMAGE`(每张扣分，默认 1)
- `HK_BASE_URL`, `HK_INTERNAL_SECRET`(须与香港一致), `HK_TIMEOUT_SECONDS`
- `MAX_UPLOAD_MB`, `CORS_ORIGINS`

backend-hk 关键项：
- `INTERNAL_SECRET`(须与国内一致)
- `OPENAI_API_KEY`, `OPENAI_IMAGE_MODEL`(gpt-image-1), `OPENAI_IMAGE_SIZE`
- `STORAGE_DIR`(图片根目录)

## 本地运行

需要 Python 3.11、Node.js、本地或远程 MongoDB。

香港网关：
```
cd backend-hk
py -3.11 -m venv .venv && .\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # 填 OPENAI_API_KEY、INTERNAL_SECRET、STORAGE_DIR
.\.venv\Scripts\uvicorn app.main:app --port 9000
```

国内主后端：
```
cd backend-cn
py -3.11 -m venv .venv && .\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # 填 MONGO_URI、JWT_SECRET、HK_BASE_URL、HK_INTERNAL_SECRET
.\.venv\Scripts\uvicorn app.main:app --port 8000
```

前端：
```
cd frontend
npm install
npm run dev        # http://localhost:5173 ，已代理 /api 到 127.0.0.1:8000
npm run build      # 产物 dist/，国内部署为静态站
```

## 验证

- 两个后端：`python -c "import app.main"` 可验证导入；启动后访问 `/health`。
- 前端：`npm run build`(含 vue-tsc 类型检查)。

## 约定

- 后端用 FastAPI + 异步 Motor；积分增减一律用 MongoDB 原子操作防并发超扣。
- 面向用户的报错文案用中文，放在 `HTTPException.detail`；前端 axios 拦截器统一弹窗(401 跳登录，402 跳充值)。
- OpenAI key 仅存在香港机器，绝不出现在国内服务或前端。
- 香港图片读取必须带内部密钥，禁止公网直接拉图。
- 新增功能(不同尺寸/套餐/不同扣分)从 `config.py` 的积分参数扩展，不要硬编码。
```
