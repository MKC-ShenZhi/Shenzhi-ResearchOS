# 个人设置 · 阶段二自动化修复说明

> **日期：** 2026-09-16  
> **分支：** `feat/personal-settings-foundation` @ `527e863`  
> **关联：** [阶段二情况说明（飞书）](https://fcnuj1ibe921.feishu.cn/wiki/OLi0w6r9XijRbokSoGecpIaMncc) · [Profile API 说明](./README.md)

本文记录阶段二代码在本机自动化验收中暴露的问题、**第一轮测试结论**、根因、修复内容与复测结果，供第二轮浏览器走查前对照。

---

## 1. 背景

阶段二（`527e863 feat: add persistent personal profiles`）已实现：

- Backend：`user_profiles` 表 + `GET/PATCH /api/v1/profile`
- Web：`ProfileEditor`、`use-user-profile`、5 张内置头像
- 测试：`test_profile_api.py`、`test_profile_persistence.py`、`settings-foundation.test.ts`

在本机 **PostgreSQL + `CHAT_DATABASE_URL` 已配置** 条件下跑全量自动化时，出现若干失败/错误。以下修复不改变阶段二产品行为，仅修复持久化遗漏、测试陈旧断言与本机/串跑环境稳定性。

---

## 2. 第一轮自动化测试结果（修复前）

**分支：** `feat/personal-settings-foundation` @ `527e863`  
**日期：** 2026-09-16

第一轮分两次执行：先在本机 PG 未就绪时做探测；补齐 PG 与迁移后再跑带真实库的 Backend 全量。Web 与 Profile 专项在两轮中均通过；Backend 全量仅在 PG 就绪后暴露 F-01～F-06。

### 2.1 子轮次 A：环境探测（PG 未就绪）

#### 应用启动

| 服务 | 状态 | 说明 |
| --- | --- | --- |
| Web `:3000` | ✅ | Next.js Ready；`GET /settings?tab=profile` → **200** |
| Backend `:8000` | ❌ | lifespan 连 PostgreSQL 被拒绝 |
| PostgreSQL | ❌ | 脚本默认 `data16:5433` 目录不存在；5432/5433 无监听 |

Backend 报错：`ConnectionRefusedError: [WinError 1225] 远程计算机拒绝网络连接`。`.env` 已配 `CHAT_DATABASE_URL`，但本机 PG 未运行。

#### 自动化结果

| 套件 | 命令 | 结果 |
| --- | --- | --- |
| Web 全量 | `pnpm test` | ✅ **174 / 174 通过** |
| Web typecheck | `pnpm typecheck` | ✅ 通过 |
| Backend 全量（未注入 DB） | `uv run python -m unittest discover -s tests` | ✅ **154 通过，20 跳过** |
| Profile API | `test_profile_api.py` | ✅ **5 / 5 通过** |
| Profile Ruff | 阶段二新增文件 | ✅ 通过 |
| Profile 持久化（带 `.env`） | `test_profile_persistence.py` | ❌ **1 ERROR**（PG 连不上） |
| Alembic 迁移 | `uv run --env-file .env alembic upgrade head` | ❌ 连接被拒绝，`004_user_profiles` 未执行 |

**Web Settings 结构测（5 项，含于 Web 全量）：** 深链 Tab、无效 tab 回退、移除 mock 传记、BFF 鉴权路径、5 张内置头像与编辑器字段覆盖 — 全部通过。

**跳过说明（20 项）：** 未向测试进程注入 `CHAT_DATABASE_URL` 时的预期 skip（Chat/Settings/Profile 持久化、部分 owner 隔离等）。

**子轮次 A 结论：** 阶段二代码层（单测 / 结构 / 类型）无失败；阻塞在 **PostgreSQL 环境**，真实 DB 持久化与 Backend 进程未能验证。

### 2.2 子轮次 B：全量跑测（PG + 迁移就绪后）

补齐环境：`127.0.0.1:5432`（`data` 目录，非脚本默认 `data16`）、Alembic → `004_user_profiles`、Backend `:8000` 与 Web `:3000` 均已启动。

#### 汇总

| 套件 | 结果 |
| --- | --- |
| Web 全量 `pnpm test` | ✅ **174 / 174 通过** |
| Web typecheck | ✅ 通过 |
| Profile 专项（`test_profile_*`） | ✅ **6 / 6 通过**（含真实 PG 持久化 + 账户隔离） |
| Web `settings-foundation.test.ts` | ✅ **5 / 5 通过** |
| Profile Ruff | ✅ 通过 |
| Backend 全量（`uv run --env-file .env python -m unittest discover -s tests`） | ❌ **154 测例：141 通过，4 失败，9 错误** |

#### 阶段二相关（Profile）— 全部通过 ✅

| 用例 | 结果 | 说明 |
| --- | --- | --- |
| `test_profile_api` ×5 | ✅ | API 契约、校验、鉴权 |
| `test_profile_persistence` ×1 | ✅ | PG 并发创建、更新、账户隔离 |
| `settings-foundation.test.ts` ×5 | ✅ | 前端结构与 BFF 接线 |

**阶段二个人 Profile 自动化在第一轮已验收通过**；Backend 全量红灯均来自环境、陈旧断言或非 Profile 模块。

#### Backend 全量失败 / 错误明细

| 结果 | 用例 / 范围 | 现象 | 对应修复 |
| --- | --- | --- | --- |
| **FAIL** | `test_settings_persistence` | 期望新用户默认 `locale=zh-CN`，读到 `en` | F-03 |
| **FAIL** | `test_acceptance_2a` · E-01 | 断言 Alembic 仍为 `002_anon_expiry_idx`，实际已 `004_user_profiles` | F-04 |
| **FAIL** | `test_acceptance_2a` · C-02 | 统计全库 `chat_messages` 行数，受其它测试/走查残留影响 | F-05 |
| **FAIL** | `test_knowledge2chat` · warnings 相关 | PG 模式下消息落库后 `warnings` 为空，断言失败 | F-02 |
| **ERROR** | `test_services.ProviderTests` 等（约 9 条） | `AI_TIMEOUT_SEC` 非纯数字 → `ValueError: could not convert string to float`；全量串跑时 Chat / Knowledge / Paper PG 集成测另现 asyncpg 连接池错误（单独跑部分可通过） | F-01、F-06 |

#### 子轮次 B 结论

| 维度 | 判定 |
| --- | --- |
| 阶段二 Profile 自动化 | ✅ 全部通过 |
| Web 整体 | ✅ 174 / 174 |
| Backend 全量绿灯 | ❌ 13 项失败/错误（见上表 → §3） |

---

## 3. 问题与修复一览

| ID | 现象 | 根因 | 修复 | 类型 |
| --- | --- | --- | --- | --- |
| F-01 | Backend 多个单测 **ERROR**（Provider、Chat API 等） | 本机 `apps/backend/.env` 中 `AI_TIMEOUT_SEC` 的值被误写成「数字 + 多余字符」（非纯数字），`float()` 解析失败 | 改为仅含数字，例如 `AI_TIMEOUT_SEC=90`（**仅本机 `.env`，勿提交 Git**） | 环境 |
| F-02 | `test_knowledge2chat` 在 PG 模式下 warnings 断言失败 | `PostgresSessionRepository.persist_message` 终态更新未写入 `warnings` 字段；流式结束后消息从 DB 读回时 warnings 为空 | 在终态 `UPDATE` 中增加 `warnings=list(message.warnings)` | **产品 Bug** |
| F-03 | `test_settings_persistence` 默认 locale 断言失败 | 测试使用固定用户 ID `settings-test-user-a`，共享开发库中已有 `locale=en` 历史行 | 测试改用 `uuid4()` 生成隔离用户 ID | 测试 |
| F-04 | `test_acceptance_2a` E-01  schema 版本失败 | 断言 Alembic 仍为 `002_anon_expiry_idx`，当前已升级至 `004_user_profiles` | 更新期望版本，并校验 `user_settings`、`user_profiles` 表存在 | 测试 |
| F-05 | `test_acceptance_2a` C-02  message 计数失败 | SQL 统计了**全库** `chat_messages` 行，受其它测试/走查残留影响 | 改为按当前 `session_id` 过滤 message | 测试 |
| F-06 | 全量串跑 5 个 PG 集成测试 **ERROR**（asyncpg 连接池） | 多个 `IsolatedAsyncioTestCase` 在 Windows 上未在 setUp/tearDown 重置 SQLAlchemy async engine | 在 Chat/Knowledge/Paper 相关测试的 setUp 调用 `dispose_engine()`，tearDown 调用 `repository.close()` | 测试 |

---

## 4. 代码改动明细

### 4.1 产品代码（需合入）

**`apps/backend/app/services/postgres_sessions.py`**

- 在 `persist_message` 的非 streaming 终态分支中，持久化 `message.warnings`。
- **影响：** 启用 PG 后，Chat 流式过程中追加的 warnings（含知识库引用校验提示）在消息完成后可从数据库正确读回；阶段二 Profile 不直接依赖此字段，但 PG 模式下 Knowledge 集成测试与 Chat 行为一致。

### 4.2 测试与验收脚本

| 文件 | 改动摘要 |
| --- | --- |
| `tests/test_settings_persistence.py` | `asyncSetUp` 用 `uuid4()` 生成 `user_a` / `user_b` |
| `tests/test_acceptance_2a.py` | E-01：版本 `004_user_profiles` + 新表；C-02：按 session 查 message |
| `tests/test_chat_api.py` | `asyncSetUp` 开头 `await dispose_engine()` |
| `tests/test_knowledge2chat.py` | 同上 |
| `tests/test_knowledge2chat_degradation.py` | setUp `dispose_engine()`；tearDown 改为 `repository.close()` |
| `tests/test_paper_assistant.py` | setUp `dispose_engine()` |

### 4.3 本机环境（不入库）

**`apps/backend/.env`**

`AI_TIMEOUT_SEC` 必须是**纯数字**（单位：秒）。编辑时不应在数字后粘贴说明文字或其它字符，否则 Backend 启动/单测会报 `ValueError: could not convert string to float`。

正确示例：

```env
AI_TIMEOUT_SEC=90
```

错误示例（值里混入了非数字内容）：

```env
AI_TIMEOUT_SEC=90……（任意后缀）
```

---

## 5. 第二轮自动化复测结果（修复后）

执行环境：本机 PostgreSQL `127.0.0.1:5432`（`shenzhi_chat`），Alembic `004_user_profiles`，`uv run --env-file .env`。

| 套件 | 命令 | 结果 |
| --- | --- | --- |
| Backend 全量 | `cd apps/backend && uv run --env-file .env python -m unittest discover -s tests` | **154 / 154 通过** |
| Profile 专项 | `test_profile_api` + `test_profile_persistence` | **6 / 6 通过** |
| Web 全量 | `cd apps/web && pnpm test` | **174 / 174 通过** |
| Settings 结构 | `tests/settings/settings-foundation.test.ts` | **5 / 5 通过**（含于 Web 全量） |
| Web 类型 | `pnpm typecheck` | **通过** |
| Profile Ruff | `ruff check`（profile 相关新增文件） | **通过** |

---

## 6. 仍未由自动化覆盖的范围（第二轮浏览器）

以下仍建议人工在浏览器验证（参见阶段二飞书说明中的「内置浏览器实测」项）：

1. **个人简介编辑闭环**：登录 → 编辑 → 保存 → 刷新/重进仍可见  
2. **列表排序**：成就/教育/机构上移下移后持久化  
3. **账户隔离**：账号 A/B 互不可见；同窗口切换账户无串号  
4. **保存失败草稿**：Backend 不可用时提示「保存失败，草稿已保留」  
5. **阶段一回归**：语言/主题偏好、硬刷新侧栏登录态（`527cd9e` 相关）

自动化已覆盖：Profile API 契约、PG 持久化与并发创建、账户隔离（服务层）、前端结构与 BFF 接线。

---

## 7. 本地跑测命令（复现用）

```powershell
# 1. PostgreSQL（本机 data 目录 + 5432，见 docs/chat/ACCEPTANCE-2a.md）
& "$env:LOCALAPPDATA\shenzhi-postgresql\pgsql\bin\pg_ctl.exe" `
  -D "$env:LOCALAPPDATA\shenzhi-postgresql\data" `
  -l "$env:LOCALAPPDATA\shenzhi-postgresql\logfile.txt" `
  -o "-p 5432 -h 127.0.0.1" start

# 2. 迁移
cd apps/backend
uv run --env-file .env alembic -c alembic.ini upgrade head

# 3. Backend 全量（必须带 --env-file 才会跑 PG 持久化测）
uv run --env-file .env python -m unittest discover -s tests

# 4. Web
cd ../web
pnpm test
pnpm typecheck
```

**注意：**

- 未配置 `CHAT_DATABASE_URL` 时，Backend 全量会有 **20 项 skip**，且无法验证 `test_profile_persistence`。  
- Alembic 须用 `uv run --env-file .env`，否则读不到 `CHAT_DATABASE_URL`。  
- `AI_TIMEOUT_SEC` 必须为纯数字，否则 Provider 相关测试全部 ERROR。

---

## 8. 后续建议（非本次修复范围）

1. 将 `docs/chat/ACCEPTANCE-2a.md` 中 E-02 期望版本同步为 `004_user_profiles`（与测试一致）。  
2. 评估是否在 `repository.clear()`（PG）或测试基类中统一 `dispose_engine()`，减少 Windows 串跑 flaky。  
3. 阶段二修复合入后，在飞书「测试落地结果」中追加 F-02 warnings 持久化条目。

---

*文档随 `feat/personal-settings-foundation` 修复提交维护；产品契约仍以 [README.md](./README.md) 为准。*
