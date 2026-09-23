# Windows 本地 PostgreSQL（Chat 持久化）

本说明对应当前分支 **`fix/local-runtime-auth-postgres`** 的唯一改动范围：让 Windows 启动脚本、`apps/backend/.env.example` 与文档中的 **端口 / 数据目录** 一致，避免 Backend 配置了 `CHAT_DATABASE_URL` 却连不上本机实例。

## 本分支包含什么

| 项 | 说明 |
|----|------|
| `scripts/start-local-postgres.bat` | 项目专用实例：`127.0.0.1:5432`，数据目录 `%LOCALAPPDATA%\shenzhi-postgresql\data`；启动或 `pg_isready` 失败时返回非零退出码 |
| `apps/backend/README.md` | 快速开始中指向本说明与脚本 |
| 本文档 | 分支目的、迁移与验收 |

## 本分支不包含什么

以下问题 **不在** 本分支 diff 中，请勿在 PR 说明里写成已修复：

- Better Auth 登录 403、`BETTER_AUTH_URL` / 浏览器 `Origin` 不一致 → 本地 `apps/web/.env.local` 配置，见 `docs/auth/CONFIGURATION.md`
- 根目录全栈启动器、`start-dev.bat`、Chat 前端 import 路径
- 主题 `ThemeMode`、Settings Client 分层
- 学者库、Knowledge 或 Vercel 环境变量

分支历史名含 `auth-postgres` 为早期命名；**合入内容以 Git diff 为准**。

## 与 `.env` 对齐

1. 复制 `apps/backend/.env.example` → `apps/backend/.env`
2. 若使用项目脚本，典型 Chat 库 URL 为：

   ```text
   CHAT_DATABASE_URL=postgresql://shenzhi:shenzhi_dev@127.0.0.1:5432/shenzhi_chat
   ```

   账号、库名以你本机初始化结果为准；**端口与脚本 `PORT` 必须一致**。

3. 启动 Backend 前（可选持久化时）：

   ```text
   ..\..\scripts\start-local-postgres.bat
   uv run alembic -c alembic.ini upgrade head
   uv run uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
   ```

## 若曾使用 5433 / `data16`

中间版本脚本曾使用 **5433** 与 **`data16`**。若你只在旧目录初始化过库，需要任选其一：

- 将 `CHAT_DATABASE_URL` 改回与旧实例一致的 host/port，并继续用旧数据目录启动；或
- 在 `%LOCALAPPDATA%\shenzhi-postgresql\data` 按项目文档重新 `initdb` / 迁移，并统一使用 **5432**。

本分支 **不会** 自动迁移数据目录。

## 验收

```powershell
# 脚本（未安装 PG 时会失败，属预期）
..\..\scripts\start-local-postgres.bat
echo $LASTEXITCODE

# 端口（PG 已启动时）
Test-NetConnection 127.0.0.1 -Port 5432

# Backend 健康（需 .env 与依赖就绪）
curl http://127.0.0.1:8000/health
```

带 PostgreSQL 的 unittest 需注入环境变量，例如：

```text
uv run --env-file .env python -m unittest discover -s tests
```

未加 `--env-file .env` 时，依赖 `CHAT_DATABASE_URL` 的用例会被 **skip**，不代表数据库不可用（见 `docs/settings/FIX-20260916-phase2-automation.md`）。

## 合并建议

- 目标分支：`dev`
- 审查重点：脚本端口策略是否与团队约定一致（与系统已有 5432 冲突时，应改 `.env` 而非强行改脚本，需维护者确认）
