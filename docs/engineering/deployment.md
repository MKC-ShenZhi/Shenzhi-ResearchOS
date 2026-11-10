# 部署与运行环境

本文描述 ShenZhi 当前的部署形态、运行环境与已知约束。改动任何部署相关配置前，先同步本文。

真实服务器 IP、上游服务地址与密钥只写在本地 `.env` 或部署平台的环境变量中，本文统一使用占位符。

---

## 一、当前形态

| 环境 | 定位 | 说明 |
|------|------|------|
| Vercel | **临时** | 目前承载 `dev` 分支的自动部署与分支预览，用于演示和联调；平台能力尚未系统梳理，见下文「下一阶段」 |
| 正式服务器 | 正式部署目标 | 配置见第三节；部署方式与运维说明由服务器负责人补充 |

原阿里云 ECS + GHCR + Watchtower 链路已完全停用，相关 `infra/` 与 GitHub Actions 配置已移除。仓库当前**没有 CI 门禁**，提交前的检查需本地执行（见 [ONBOARDING](../../ONBOARDING.md)）。

---

## 二、Vercel（临时）

### 架构

```text
浏览器
  │  (仅访问同源 Next.js BFF /api/v1,不直接接触后端)
  ▼
shenzhi.vercel.app ──── Vercel 项目 shenzhi (apps/web, Next.js)
  │  服务端携带 x-shenzhi-bff-secret 调用
  ▼
shenzhi-backend.vercel.app ──── Vercel 项目 shenzhi-backend (apps/backend, FastAPI Serverless)
  │
  ▼
Vercel Postgres (Neon):Auth 表与业务表共存于同一库
```

| Vercel 项目 | 根目录 | 域名 | 说明 |
|------|------|------|------|
| `shenzhi` | `apps/web` | https://shenzhi.vercel.app | Next.js 前端 + BFF |
| `shenzhi-backend` | `apps/backend` | https://shenzhi-backend.vercel.app | FastAPI,以单个 Python Serverless Function 运行(`apps/backend/api/index.py` 导出 ASGI app,`apps/backend/vercel.json` 将全部路径 rewrite 至该函数,`maxDuration=300`) |

### 分支与部署映射

| Git 分支 | 部署级别 | 访问入口 |
|------|------|------|
| `dev` | Production Branch | `shenzhi.vercel.app` / `shenzhi-backend.vercel.app` |
| 其他分支 | Preview | `shenzhi-git-<分支名>-hakrin-devs-projects.vercel.app`(分支别名,随该分支最新部署移动) |
| 任意单次部署 | 固定快照 | `shenzhi-<哈希>-hakrin-devs-projects.vercel.app`(不可变,用于定位历史版本) |

- push 到 GitHub 自动构建;两个项目的 `dev` 分支另配置了 Deploy Hook(见各项目 Settings → Git → Deploy Hooks)。
- 预览环境已关闭 Deployment Protection,预览 URL 无需登录 Vercel 即可访问;PR 中 Vercel bot 会评论预览链接。
- 后端构建使用 Vercel 原生 uv 支持:依据 `apps/backend/uv.lock` 安装依赖、`.python-version` 选定 Python 3.12,不另行添加 `requirements.txt`。

### 环境变量规则

1. 变量清单与含义以 [apps/web/.env.example](../../apps/web/.env.example) 与 [apps/backend/.env.example](../../apps/backend/.env.example) 为准,真实值只注入 Vercel(Settings → Environment Variables),不入库。
2. 除 `BETTER_AUTH_URL`、`BUSINESS_BACKEND_URL` 按环境拆值(Production 与 Preview 各一条)外,所有变量同时勾选 Production + Preview,否则预览环境会出现「功能缺失型」故障(如邮件未配置、知识底座不可用)。
3. 修改变量后必须 Redeploy 才生效;`NEXT_PUBLIC_` 前缀变量在构建期内联,需重新部署前端项目。
4. 后端 `CHAT_DATABASE_URL` 使用 Neon 连接串时,`channel_binding=require&sslmode=require` 需改写为 `?ssl=require`(asyncpg 不识别原参数)。
5. `BACKEND_BFF_SECRET` 两端必须一致;`BACKEND_ALLOW_INSECURE_LOCAL_BFF` 仅限本机 loopback 联调,线上不开启。

### 限制与已知事项

1. **Serverless 与进程内运行时不匹配**。后端按长驻进程设计,以下能力在 Vercel 上不保证可用:
   - `lifespan` 不保证执行，启动时的 `recover()` 与进程内后台调度器可能不运行。Vercel 演示环境保持 `BACKGROUND_JOBS_ENABLED=false`。手动维护命令见 [后端 README](../../apps/backend/README.md)。
   - 函数单次执行上限 300s;Agent 的 deep / idea / doubt 模式运行时限为 900s(`services/agent/policies.py`)。
   - Agent 运行归属保存在单进程内存(`services/agent_sessions/live.py`),重连、steer、stop 请求可能落到其他实例。
   - Agent workspace 写本地磁盘(`apps/backend/workspace/`),Serverless 下不持久。
2. **会话与附件**:`CHAT_DATABASE_URL` 必须配置,缺失时会话退化为函数内存态(接口返回 `ephemeral: true`)。Agent 附件只将解析文本短暂写入数据库,不保存源文件。
3. **知识底座可达性**:`KNOWLEDGE_BASE_API_URL` 必须是公网可达地址(Vercel 函数位于美国机房);上游不可用时接口显式报错,不返回 mock 数据。
4. **数据库分支陷阱**:`shenzhi` 项目已断开与 Neon 集成的连接并改用手动 `DATABASE_URL`。不要重新连接该集成,其「预览分支」会向预览部署注入未迁移的独立库,表现为 `relation "verification" does not exist`。
5. **国内网络访问**:`*.vercel.app` 在国内存在 DNS 污染与阻断,访问需可上外网的网络环境;`api.vercel.com` 国内可直连。
6. **邮件 / OAuth 回调**:`AUTH_EMAIL_FROM` 必须在阿里云 DirectMail 完成验证;GitHub OAuth App 回调地址须与访问域名匹配(`https://shenzhi.vercel.app/api/auth/callback/github`)。

### 回滚与排障

- 回滚:对历史健康部署执行 `vercel promote <部署URL>`(需 Vercel CLI 登录),约 10 秒切换生产指向。
- 健康探针:`GET https://shenzhi-backend.vercel.app/health` 返回 `{"status":"ok"}`。
- 日志:Vercel 项目 → Logs(需账号权限),或 `vercel logs <部署URL> [--follow]`。

---

## 三、正式服务器

| 项目 | 配置 |
|------|------|
| CPU | 2 vCPU(Intel Xeon Cascade Lake,约 2.89 GHz,支持 AVX2 / AVX-512) |
| 内存 | 约 4 GB(3.8 GiB) |
| 交换空间 | 7.7 GiB |
| 磁盘 | 80 GiB 虚拟磁盘 |
| GPU | 无计算 GPU |
| 系统 | Ubuntu 22.04.5 LTS(虚拟机) |

服务器地址与登录方式不入库,向服务器负责人获取。

完成数据库迁移后，正式常驻后端设置 `BACKGROUND_JOBS_ENABLED=true`，统一启动首页数据任务和会议 DDL 同步。此开关默认关闭。已有部署升级时，用它替换原来的 `HOME_FEED_SCHEDULER_ENABLED` 和 `CONFERENCE_SYNC_ENABLED`。

---

## 四、下一阶段

- 梳理 Vercel 的能力边界,将其定位为**开发测试环境**:在正式部署前暴露构建、配置与运行问题。
- 明确正式服务器的部署方式,并据此处理第二节「Serverless 与进程内运行时不匹配」中的各项约束。

相关待收敛项见 [已知偏移与待收敛项](known-gaps.md)。
