# ShenZhi 新人上手指南

欢迎加入深知（ShenZhi）项目组。本文帮你在最短时间内跑起本地开发环境、理解协作流程、知道遇到问题去哪查。预计阅读 15 分钟，环境搭建 30 分钟。

---

## 一、这个项目是什么

深知是面向人工智能领域学术科研的专业可信知识智能体服务平台，提供论文检索、投稿筛选，以及 Deep Research / Auto Research 知识智能体服务。仓库是 monorepo：

```
shenzhi/
├── apps/
│   ├── web/            # Next.js 16 前端 + BFF(浏览器只访问它的 /api/v1)
│   └── backend/        # FastAPI 核心业务后端(Agent 对话 / 知识库 / 个人数据 / 首页 Feed)
├── data/ scripts/      # 离线数据源与数据发布脚本
├── docs/               # 工程规范、模块文档、PRD 与历史记录
├── tests/ tools/       # 视觉验证脚本、品牌资产工具
├── README.md           # 项目总览、路由与技术栈
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

可选 Docker 路线：先运行 `python infra/docker/prepare-env.py`（已有本机配置加 `--from-local`），
再进入 `infra/docker`。仅数据库使用 `docker compose up -d --wait postgres`，应用仍按下文原生启动；
完整容器开发使用 `docker compose -f compose.yml -f compose.dev.yml --profile full up -d --build --wait`。
首次启动自动执行独立迁移服务；新数据库不复制原生账号和套餐权益。
Windows 使用 Docker Desktop 的 Linux containers / WSL2 后端，完整说明见
[Docker 运行指南](infra/docker/README.md)。停止用 `down` 保留数据，禁止把 `down -v` 当日常命令。

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
uv run --env-file .env alembic upgrade head   # 配置 CHAT_DATABASE_URL 后执行数据库迁移
uv run uvicorn app.main:app --env-file .env --reload --host 127.0.0.1 --port 8000
```

会话、收藏、阅读记录等持久化能力需要 PostgreSQL:在 `.env` 中配置 `CHAT_DATABASE_URL` 并执行迁移;未配置时会话退化为进程内存态。Windows 可参考 `scripts/start-local-postgres.bat` 启动本地实例(可用 `PG_BIN` 指定 PostgreSQL 安装目录)。

### 3.4 提交前的检查

```bash
cd apps/web && pnpm typecheck && pnpm lint && pnpm test
cd apps/backend && uv run python -m compileall app && uv run python -m unittest discover -s tests -v
```

改动哪个范围就跑哪个范围的检查。仓库当前没有 CI 门禁，提交前需在本地执行，评审以此为准。

## 四、Git 协作流程

```
dev ──┬── feat/xxx、fix/xxx 等(你的工作分支,从最新 dev 切出)
      ▲
      └── PR 评审后合回 dev ──(管理员定期)──▶ main
```

- **日常开发在工作分支上进行**（`feat/`、`fix/`、`refactor/`、`docs/` 等），从 `origin/dev` 创建：`git checkout -b feat/my-feature origin/dev`
- 完成后在 GitHub 开 PR → 目标分支 `dev` → 找同学评审
- **不要直接 push 到 `dev` / `main`**
- Commit 格式：`<type>: <中文描述>`，type 用 `feat/fix/refactor/docs/chore/test`，例如 `feat: 新增论文收藏功能`；一个 commit 对应一个明确目的
- 完整细则：[docs/engineering/git-conventions.md](docs/engineering/git-conventions.md)

## 五、线上环境

日常开发和分支联调使用本地环境。正式环境位于韩国服务器，访问地址和发布流程向服务器负责人确认。修改部署配置前，先同步 [部署与运行环境](docs/engineering/deployment.md)。

## 六、遇到问题去哪查

| 问题类型 | 去处 |
|----------|------|
| 部署/环境变量/线上限制 | [docs/engineering/deployment.md](docs/engineering/deployment.md) |
| 工程架构与分层 | [docs/engineering/architecture-confirmation.md](docs/engineering/architecture-confirmation.md) |
| 后端能力、首页 Feed、Knowledge 接入 | [apps/backend/README.md](apps/backend/README.md) |
| 深知 AI（Agent）对话 | [docs/agent/README.md](docs/agent/README.md) |
| 认证体系 | [docs/auth](docs/auth) |
| 各模块文档索引 | [docs/README.md](docs/README.md) |
| Git 流程 | [docs/engineering/git-conventions.md](docs/engineering/git-conventions.md) |

## 七、常见坑（新人高发）

1. **改了环境变量不生效** → 确认改的是 `.env.local`（Web）或 `.env`（Backend），然后重启对应的本地服务。生产 Web 的 `NEXT_PUBLIC_*` 变量需要重新构建。
2. **本地起后端后前端仍报 503** → 两端都要设 `BACKEND_ALLOW_INSECURE_LOCAL_BFF=true`，且 `BUSINESS_BACKEND_URL` 是 `http://127.0.0.1:8000`
3. **Windows 上 `pnpm dev` 报 Turbopack 二进制被拦截** → 换到 WSL2 内开发
4. **知识检索报"暂不可用"** → 确认已配置 `KNOWLEDGE_BASE_API_URL`，并检查后端能否访问该地址。
