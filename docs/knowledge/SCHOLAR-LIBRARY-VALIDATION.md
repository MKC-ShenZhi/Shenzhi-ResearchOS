# 任务1-学者库

工作规划、自动化测试结果与人工验收表单。

> 基线：`origin/feat/knowledge-entity-refactor@3ef4564`  
> 开发分支：`feat/knowledge-scholar-library`（基于 `feat/knowledge-entity-refactor`，完成后合并回该父分支）  
> 验证日期：2026-09-23

## 1. 当前代码现状

学者库已经不是原型数据页面。正式调用链为：

```text
/knowledge/scholars
→ apps/web/clients/knowledge
→ 同源 /api/v1/knowledge/* BFF
→ FastAPI Knowledge API / Service
→ integrations/knowledge
→ 知识底座 Scholar API
```

已具备：真实姓名检索、学者详情、论文成果跳转、合作学者跳转、加载态、空结果、错误态、一次受控重试，以及 opaque ID 编解码边界。当前公开字段仅包括上游明确提供的姓名、论文数、年份、会议、主题、基金、机构、合作学者和论文；不虚构 h-index、引用数、履历、角色、邮箱或主页。

已修复的两个边界问题：对已人工确认的 `何恺明` 使用 Knowledge Service 内的精确英文名映射；学者详情 API 改为捕获完整 opaque ID 路径，支持 ID 中包含斜杠等字符。未知中文姓名仍原样发送，不猜测或自动翻译。知识底座全量中文姓名召回能力仍需与上游确认。

## 2. 工作规划

### 阶段 A：稳定性与契约验收

1. 固化学者 Search、Detail、空结果、错误码和 opaque ID 自动化测试。
2. 自动化验证姓名映射和空结果契约；使用真实环境对照典型英文姓名、中文姓名和不存在姓名。
3. 核对详情中所有可选字段；上游未返回的字段必须隐藏，不显示伪造的零值或占位事实。
4. 验证学者到论文、合作学者的完整导航与返回路径。

### 阶段 B：中文姓名问题定界

1. 对同一学者分别使用中文名、英文名和常见英文变体检索，并记录请求、结果数和首条 ID。
2. 若知识底座可以稳定支持中文名，产品侧不增加 Rewrite。
3. 若知识底座不能支持中文名，先向知识底座组确认正式能力和姓名词典来源。
4. 对已确认姓名在 FastAPI Knowledge Service Query 层做精确 Rewrite；不得放在页面、BFF 或 Integration transport 中，也不得维护无法追溯的个人名单。

### 阶段 C：修复与回归

1. 只修复验收中确认的问题，不扩展学者关注、关系图谱或虚构画像字段。
2. 运行学者专项、Web 全量测试、Backend 相关测试、typecheck 和 lint。
3. 人工浏览器验收通过后，将 PR 合并回 `feat/knowledge-entity-refactor`。

## 3. 自动化测试表单

每次复测在项目后填写“通过 / 失败 / 阻塞”和证据。

### A01 中文与英文 Query 契约

- 类型：自动化
- 覆盖：首尾空格归一化；Unicode 中文姓名不被损坏；Query 当前原样进入 Integration。
- 命令：`uv run python -m unittest tests.test_knowledge_entities -v`
- 当前结果：通过；本轮专项共 21 项通过。
- 说明：此项验证传输正确，不代表上游能够命中中文姓名。

### A02 学者 Search 和 Detail 契约

- 类型：自动化
- 覆盖：Search/Detail 端点、limit/offset、字段映射、opaque ID、缺省可选数组。
- 命令：同 A01。
- 当前结果：通过；包括含斜杠、中文和问号的 opaque ID 经 API 详情路由往返。

### A03 空结果与异常映射

- 类型：自动化
- 覆盖：空结果为成功响应；TIMEOUT 可重试；NOT_FOUND 不可重试；非法参数返回 `INVALID_ARGUMENT`。
- 命令：同 A01。
- 当前结果：通过；空结果、错误映射和参数校验均覆盖。

### A04 前端状态与跳转

- 类型：自动化
- 覆盖：初始态、loading、zero-result、error、重试入口、论文链接、合作学者链接、opaque ID 路由恢复。
- 命令：`corepack pnpm test`
- 当前结果：通过；Web 套件含学者链接编解码、页面状态及导航契约测试，但不是浏览器 E2E。

### A05 静态类型与全量回归

- 类型：自动化
- 命令：`corepack pnpm typecheck`、`corepack pnpm test`、`corepack pnpm lint`。
- 当前结果：typecheck 通过；Web 221 项测试全部通过；本次修改文件 Ruff 检查通过。未重跑 Web lint；上次基线为 0 error、2 个无关 warning。
- Lint 基线 warning：`features/chat/hooks/use-chat-session.ts` 缺少 `setBusyValue` dependency；`lib/use-popover-placement.ts` 缺少 `anchorRef` dependency，均与学者库无关。

### A06 Backend 全量基线

- 类型：自动化
- 命令：`uv run python -m unittest discover -s tests -v`。
- 当前结果：本轮执行 `uv run python -m unittest discover -s tests -v`，未使用 `--env-file .env`。因此 21 项依赖 PostgreSQL 的用例被 `skipUnless(os.getenv('CHAT_DATABASE_URL'))` 跳过；这是测试进程环境注入差异，不是数据库连接失败，也不是 `.env` 缺少配置。302 项通过，另有 1 个既有导入错误（`app.services.reading_history` 缺失）和 1 个既有 Deep Research Windows CRLF/LF 断言失败。项目约定的带库跑法见 `docs/settings/FIX-20260916-phase2-automation.md`；若要验证数据库本身，使用 `uv run --env-file .env python -m unittest discover -s tests`，并确保 PostgreSQL 已启动且迁移完成。本轮没有执行该带库验证。
- 学者专项影响：无；`test_knowledge_entities` 独立通过。

## 4. 人工浏览器测试表单

### 准备

1. 启动 FastAPI，并配置真实 `KNOWLEDGE_BASE_API_URL` 与 BFF 凭据。
2. 启动 Web，确保 `NEXT_PUBLIC_KNOWLEDGE_SOURCE=bff`。
3. 打开浏览器开发者工具的 Network 和 Console。
4. 进入 `/knowledge/scholars`。

### M01 英文姓名正常检索

1. 输入 `Geoffrey Hinton` 并搜索。
2. 预期出现加载态，随后出现真实结果；页面无控制台错误。
3. Network 只出现同源 `/api/v1/knowledge/scholars/search?...`，不得出现知识底座公网地址。
4. 记录结果数、首条姓名、论文数和请求 ID。

### M02 中文姓名对照检索

1. 输入一个已知中文学者名，例如 `何恺明`。
2. 记录结果数和首条 ID。
3. 再输入其英文名 `Kaiming He`，记录相同信息。
4. 若中文为零、英文有结果，判定“中文姓名检索缺口”复现；不要把空结果误判为前端故障。

### M03 空结果

1. 输入确定不存在的长随机姓名。
2. 预期显示“未找到匹配的学者”，不显示错误卡片，不回退到 Mock 数据。

### M04 搜索错误与重试

1. 在测试环境临时使用不可达 Knowledge Base 地址，或通过浏览器离线模式触发失败。
2. 预期显示安全的错误信息和“重试”入口；页面不得暴露上游 URL、密钥、traceback。
3. 恢复网络后点击重试，预期可以重新请求。

### M05 学者详情字段

1. 从搜索结果进入详情。
2. 核对姓名、论文数、年份、会议、主题、机构、基金、论文和合作学者是否与响应一致。
3. 响应中为空的 section 应完全隐藏；论文与合作学者均为空时显示统一空态。
4. 不应出现 h-index、引用数、邮箱、个人主页或虚构履历。

### M06 论文跳转

1. 点击详情中的一篇论文。
2. 预期进入 `/papers/<opaque-id>`，论文可正常加载。
3. URL 应携带返回来源；返回后应回到当前学者详情。

### M07 合作学者跳转

1. 点击一个合作学者。
2. 预期进入对应 `/knowledge/scholars/<opaque-id>`，不是回到原学者或首条静态数据。
3. 浏览器前进、后退后页面和 URL 保持一致。

### M08 响应式与可访问性冒烟

1. 分别使用 375px、768px 和桌面宽度检查搜索框、按钮、结果卡和详情双栏。
2. 仅使用键盘完成输入、搜索、进入结果、返回。
3. 焦点应可见，无横向溢出；搜索按钮在空输入时禁用。

## 5. M01-M08 自动化覆盖状态

自动化测试验证 API / Service / 前端代码契约，不等同于真实浏览器 E2E。以下“部分通过”表示该场景的可自动化契约有测试，人工步骤仍未执行。

- M01 英文姓名正常检索：部分通过。Scholar Search API / Adapter 映射、前端 BFF 请求边界已由自动化测试覆盖；真实知识底座响应、Network 与 Console 检查未自动完成。
- M02 中文姓名对照检索：部分通过。`何恺明` 精确映射至 `Kaiming He`、分页参数保留以及未知中文名透传有 Backend 单测；真实上游中英文返回相同 Scholar ID 尚未在本轮自动验证。
- M03 空结果：部分通过。Backend 空 results 成功响应及前端空结果状态契约有测试；浏览器实际显示未做 E2E。
- M04 搜索错误与重试：部分通过。上游 TIMEOUT / 错误码映射及 UI 错误、重试入口有自动化契约覆盖；断网后恢复并点击重试未做浏览器 E2E。
- M05 学者详情字段：部分通过。字段映射、可选数组缺省、契约异常及空状态显示规则有测试；真实上游字段逐项核对未完成。
- M06 论文跳转：部分通过。论文链接使用 opaque ID 与返回来源的前端契约有测试；浏览器实际加载论文及后退恢复未做 E2E。
- M07 合作学者跳转：自动化契约通过。前端 opaque ID 编解码用例覆盖 slash、中文、问号；本轮新增 Backend API 用例确认编码 ID 完整到达详情服务。浏览器历史导航未做 E2E。
- M08 响应式与可访问性：未自动完成。现有 Node 测试和 typecheck 不会布局页面或驱动键盘；375/768/桌面视口、焦点可见性和键盘流程仍需人工浏览器验收。

## 6. 本轮测试报告

- 学者专项 Backend：21 项通过，0 失败。
- Web 全量测试：221 项通过，0 失败。
- Web TypeScript typecheck：通过。
- Ruff（本次 Backend 修改文件）：通过。
- Backend 全量：325 项运行，302 项通过、21 项因 unittest 未通过 `--env-file .env` 注入 `CHAT_DATABASE_URL` 而跳过、1 项导入错误、1 项 Deep Research 换行断言失败；两项失败均不属于学者库。该 skip 不能说明数据库连接状态；本轮未运行带库测试。
- 真实知识底座与浏览器人工验收：M01-M08 对应未完成项见上表，重点是中英文同 ID 对照、真实详情字段、Network/Console、交互导航和响应式键盘流程。

当前结论：学者库的 API / Service 契约和 opaque ID 详情边界已有自动化回归；已确认的中文姓名问题由一项精确映射兜底。测试没有冒充真实浏览器验收；M01-M06 仍需真实环境确认，M08 需人工完成。

## 7. 代码说明

- `apps/backend/app/services/knowledge/service.py`：在现有 Knowledge Service 对已审核姓名做精确查询映射，保持 Adapter、API 和响应契约不变；未知姓名原样透传。
- `apps/backend/app/api/knowledge.py`：学者详情路由使用 path 参数接收完整 opaque ID，避免 ID 含 `/` 时路由 404。
- `apps/backend/tests/test_knowledge_entities.py`：覆盖已确认映射、未知姓名透传、上游错误语义，以及编码后的含 slash / Unicode / query 字符 ID 经过 API 的回归。
- 无新增依赖、数据库表、迁移、日志框架或前端科研服务直连。
