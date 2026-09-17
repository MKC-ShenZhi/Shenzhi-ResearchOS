# ShenZhi 新人上手指南

欢迎加入深知（ShenZhi）项目组。本文帮你在最短时间内跑起本地开发环境、理解协作流程、知道遇到问题去哪查。预计阅读 15 分钟，环境搭建 30 分钟。

---

## 一、这个项目是什么

深知是面向人工智能领域学术科研的专业可信知识智能体服务平台，提供论文检索、投稿筛选，以及 Deep Research / Auto Research 知识智能体服务。仓库是 monorepo：

```
shenzhi/
├── apps/
│   ├── web/            # Next.js 16 前端 + BFF(浏览器只访问它的 /api/v1)
│   └── backend/        # FastAPI 业务后端(Chat / 知识检索 / 模型流 / 附件解析)
├── infra/              # ECS + Docker 备用部署链路(当前未启用)
├── docs/               # PRD、工程规范、各能力文档
├── tests/ tools/       # 视觉验证脚本、品牌资产工具
├── README.md           # 项目总览 + 部署文档(部署问题看这里)
└── ONBOARDING.md       # 本文
```

**职责边界（重要）**：页面与交互归 `apps/web`，核心业务逻辑与数据处理归 `apps/backend`；前端不直连数据库、不直连第三方科研服务，一律经 `clients/` → Next.js BFF → FastAPI。

## 二、先读这三份规则

1. 根目录 [AGENTS.md](AGENTS.md)：全仓库协作原则
2. [docs/engineering/git-conventions.md](docs/engineering/git-conventions.md)：分支、Commit、合并流程
3. 你主要工作目录下的 `AGENTS.md`（如 [apps/web/AGENTS.md](apps/web/AGENTS.md)、[apps/backend/AGENTS.md](apps/backend/AGENTS.md)）：更具体的局部约束

## 三、本地环境搭建

### 3.1 前置要求

| 工具 | 版本 | 说明 |
|------|------|------|
| Node.js | ≥ 22 | 建议用 nvm 管理 |
| pnpm | 11 | `npm i -g pnpm` |
| Python | ≥ 3.12 | |
| uv | 最新 | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Git | — | 远程仓库 `git@github.com:MKC-ShenZhi/Shenzhi-ResearchOS.git` |

使用 Windows 的同学建议在 **WSL2** 内开发（仓库在 WSL 文件系统内，Turbopack 与脚本兼容性最好）。

### 3.2 启动前端

```bash
git clone git@github.com:MKC-ShenZhi/Shenzhi-ResearchOS.git
cd Shenzhi-ResearchOS/apps/web
pnpm install
cp .env.example .env.local   # 本地开发用,按下表填最小集
pnpm dev                     # http://localhost:3000
```

本地最小环境变量（`.env.local`）：

```text
BUSINESS_BACKEND_URL=http://127.0.0.1:8000
BACKEND_ALLOW_INSECURE_LOCAL_BFF=true   # 仅本机联调,后端同样设置
BETTER_AUTH_SECRET=<随便一个32位以上随机串>
BETTER_AUTH_URL=http://localhost:3000
```

> 不配置数据库和邮件密钥也能启动；登录、验证码等能力在本地属于"可启动但调用会安全失败"的状态，需要完整联调时找管理员要开发用密钥。

### 3.3 启动后端（需要 AI 对话/知识能力时）

```bash
cd apps/backend
uv sync
cp .env.example .env         # 填 DASHSCOPE_API_KEY 或 DEEPSEEK_API_KEY 等
uv run uvicorn app.main:app --env-file .env --reload --host 127.0.0.1 --port 8000
```

### 3.4 提交前的检查

```bash
cd apps/web && pnpm typecheck && pnpm lint && pnpm test
cd apps/backend && uv run python -m compileall app && uv run python -m unittest discover -s tests -v
```

改动哪个范围就跑哪个范围的检查；CI 与评审以此为准。

## 四、Git 协作流程

```
dev ──┬── feat/xxx (你的功能分支,从最新 dev 切出)
      ▲
      └── PR 评审后合回 dev ──(管理员定期)──▶ main
```

- **日常开发只碰 `feat/*` 分支**，从 `origin/dev` 创建：`git checkout -b feat/my-feature origin/dev`
- 完成后在 GitHub 开 PR → 目标分支 `dev` → 找同学评审
- **不要直接 push 到 `dev` / `main`**
- Commit 格式：`<type>: <中文描述>`，type 用 `feat/fix/refactor/docs/chore/test`，例如 `feat: 新增论文收藏功能`；一个 commit 对应一个明确目的
- 完整细则：[docs/engineering/git-conventions.md](docs/engineering/git-conventions.md)

## 五、线上环境地图

| 环境 | 地址 | 内容来源 | 用途 |
|------|------|----------|------|
| 生产 | https://shenzhi.vercel.app | `dev` 分支（临时，见 README 部署章节） | 对外展示与验收 |
| 后端生产 | https://shenzhi-backend.vercel.app/health | `dev` 分支 | 前端 BFF 调用，不直接对外 |
| 你的分支预览 | `shenzhi-git-<分支名>-hakrin-devs-projects.vercel.app` | push 后自动生成 | 给别人验收你的功能 |

- PR 里 Vercel bot 会自动评论预览链接，直接发给测试同学即可（预览无需登录）
- ⚠️ `*.vercel.app` 在国内被 DNS 污染，访问需要可上外网的网络环境
- 部署配置、环境变量规则、已知限制：**必读 [README.md](README.md) 的部署章节**，改部署配置前先同步该文档
- Vercel 后台/日志权限在管理员处，需要查看日志或配环境变量找管理员协助

## 六、遇到问题去哪查

| 问题类型 | 去处 |
|----------|------|
| 部署/环境变量/线上限制 | [README.md 部署章节](README.md) |
| 后端能力、Knowledge 接入 | [apps/backend/README.md](apps/backend/README.md) |
| Chat 架构、SSE 协议 | [docs/chat/README.md](docs/chat/README.md) |
| 认证体系 | [docs/auth](docs/auth) |
| ECS 备用部署 | [infra/README.md](infra/README.md) |
| Git 流程 | [docs/engineering/git-conventions.md](docs/engineering/git-conventions.md) |

## 七、常见坑（新人高发）

1. **改了环境变量不生效** → Vercel 上必须 Redeploy；本地确认改的是 `.env.local`（web）/ `.env`（backend）
2. **本地起后端后前端仍报 503** → 两端都要设 `BACKEND_ALLOW_INSECURE_LOCAL_BFF=true`，且 `BUSINESS_BACKEND_URL` 是 `http://127.0.0.1:8000`
3. **push 后没有预览部署** → 确认分支名不是 `main`/`dev` 以外的保护例外；到 Vercel 项目 Deployments 看构建日志（需权限，找管理员）
4. **Windows 上 `pnpm dev` 报 Turbopack 二进制被拦截** → 换到 WSL2 内开发
5. **知识检索报"暂不可用"** → 先确认 `KNOWLEDGE_BASE_API_URL` 已配且公网可达，再怀疑代码
