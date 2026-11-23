# M0-R1-B：多次 Run 重试后的 Session SSE 恢复游标

日期：2026-11-18。M0-R1-B 已提交并推送审查分支；用户已确认 ChatGPT 独立代码审查通过。此结论不代表 M0-C 真实环境验收通过，M0 整体仍为 PARTIAL。

当前交接基线：本地分支 `feat/agent-m0-integration`，HEAD 为 `1d1bc7e0ea7791ba3abe6aa529a13ade1be6ed8f`；审查分支为 `review/m0-r1-b`。相对原 dev 基线 `5faee7e71bb14e7d6943dab1e2e342af61bd7581` 的 M0 工作尚未合入 dev。本次交接仅改文档，未再次 Commit / Push。后续执行入口见 [M0 交接](../../../agent/m0-handoff.md)。

## 修复实施时的基线与范围（历史记录）

- 分支：`feat/agent-m0-integration`
- 修复前 HEAD：`6ccd0d95a91795098158c700c0f594cc45923206`；修复提交为 `1d1bc7e0ea7791ba3abe6aa529a13ade1be6ed8f`。
- 修复开始时工作区干净；实施结束时的修改随后全部纳入上述提交，推送后工作区干净。未创建分支或 Worktree，未执行 merge / rebase，未修改 dev。
- 未修改 Web UI、Runtime / Worker 事件生成、数据模型、迁移或依赖锁文件；未启动服务或连接外部数据库。

## 根因与修复

旧投影从关联 Run 开始，每次终态后直接跳至 Task 的 `current_run_id`。轮询之间完成多次重试时，中间 Run 被漏掉；无缓存重建后的事件数量和 SSE ID 因此缩短。

新增只读内部接口 `GET /internal/v1/tasks/{task_id}/runs?owner_id=...` 和共享 `TaskRunsResponseWire`，完整返回按现有 `attempt` 升序排列的 Run ID。沿用服务认证、Task Owner 校验和 `(task_id, attempt)` 唯一约束，不分页、不按时间或最新 Run 推断历史。Backend 只调用 Gateway，不访问 Agent 数据库。

首次与恢复 Session 投影都从最早 Run 开始，排空旧 Run 后只进入列表中的直接后继。Control 已在同一事务提交终态报告与重试 Run，因此观察到终态后枚举可以确定后继。保留 M0-R1-A 的“先读状态、再读事件”顺序，确保旧 Run 尾部完整。

产品流按 Run 顺序发送一条产品 run_start 和该 Run 按 seq 排序的全部持久事件，最后只生成一条产品 result。LiveRun 零基索引及 after 语义不变；每个 Run 有 Nᵢ 条事件时，result ID 为 Σ(1 + Nᵢ)。三 Run、每 Run 一条事件的 result ID 始终为 6：未收到 result 使用 after=6，完整收到后使用 after=7。

## 文件

- `apps/agent/src/agent_app/api/routes.py`
- `apps/agent/src/agent_app/control/repository.py`
- `apps/agent/tests/unit/test_task_runs.py`（新增）
- `apps/backend/app/services/agent_gateway/client.py`
- `apps/backend/app/services/agent_sessions/service.py`
- `apps/backend/tests/test_agent_contracts.py`
- `apps/backend/tests/test_agent_sessions.py`
- `apps/backend/tests/test_agent_sse_tail.py`
- `apps/backend/tests/test_agent_sse_retries.py`（新增）
- `packages/agent-contracts/src/agent_contracts/wire.py`
- `packages/agent-contracts/src/agent_contracts/__init__.py`
- `packages/agent-contracts/tests/test_wire.py`
- `docs/agent/contracts.md`
- `docs/agent/session-persistence.md`
- 本记录。

## 命令与结果

在 `apps/backend` 执行：

```powershell
$env:PYTHONPATH="../../packages/agent-contracts/src"
uv run --frozen --no-sync python -m unittest tests.test_agent_sse_retries tests.test_agent_sse_tail tests.test_agent_contracts -q
# 23 通过，0 失败
uv run --frozen --no-sync python -m unittest tests.test_agent_sessions tests.test_agent_api tests.test_agent_persistence tests.test_anonymous_claim tests.test_agent_uploads -q
# 28 通过，13 跳过，0 失败（共 41 项）
```

在 `apps/agent` 执行：

```powershell
$env:PYTHONPATH="src;../../packages/agent-contracts/src"
uv run --project ../backend --frozen --no-sync python -m unittest tests.unit.test_task_runs tests.unit.test_worker_takeover -q
# 11 通过，0 失败；真实 Control SQL，SQLite 内存库
```

在 `packages/agent-contracts` 执行：

```powershell
$env:PYTHONPATH="src"
uv run --project ../../apps/backend --frozen --no-sync --with pytest==9.2.0 --index-url https://pypi.org/simple python -m pytest tests/test_wire.py -q
# 7 通过，0 失败，1 条既有 anyio / pytest 弃用警告
```

最终测试合计：69 通过、0 失败、13 跳过。新增 13 个测试方法/函数，另有参数子场景。覆盖一至三个 Run、中间失败/超时、首次/恢复活跃投影、缓存丢失、全部 after 偏移及 result 前后边界、旧 Run 尾部、Owner 隔离、服务认证、时间戳逆序下的完整枚举、M0-R1-A SSE 与 Worker 回归。

根目录执行 `git diff --check` 通过；`git status --short`、`git branch --show-current`、`git rev-parse HEAD` 确认基线未移动。

前期测试启动受 uv 缓存沙箱权限和现有环境未安装 agent-contracts 影响，曾产生 3 个模块导入错误，后通过源码 PYTHONPATH 和获准的本地测试执行解决。Agent 原命令 `uv run --frozen pytest tests/unit/test_task_runs.py tests/unit/test_worker_takeover.py ../../packages/agent-contracts/tests/test_wire.py -q` 在同步依赖时被镜像源 python-dotenv 下载 403 阻断；后复用 Backend 环境。契约测试首次复用环境路径写错为 `../backend`，修正为 `../../apps/backend` 后通过。上述启动失败不计入最终通过数，也没有修改锁文件。

## 限制与风险

- Agent API 需先具备新增只读接口，再运行依赖它的 Backend；旧 Agent API 没有此接口。
- 未执行真实 PostgreSQL、多进程和独立服务联调；13 个 PostgreSQL 持久化测试因未配置 CHAT_DATABASE_URL 跳过。
- Agent 测试复用现有 Backend 依赖环境，不能等同于 Agent 锁文件完整安装后的验证。
- 稳定重建依赖既有历史 Run / 事件不可变且保留、报告与重试原子提交的约定；不修复旧版本已经发出的缺失事件流游标。未关联 Task 的历史导入和无状态 `/run` API 保持原行为。
