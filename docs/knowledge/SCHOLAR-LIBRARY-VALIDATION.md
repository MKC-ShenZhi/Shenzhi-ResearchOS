# 学者库工作规划与测试报告

> 基线：`origin/feat/knowledge-entity-refactor@3ef4564`  
> 验证分支：`codex/scholar-library-validation`  
> 验证日期：2026-09-22

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

已确认的主要缺口：中文姓名当前会原样发送给知识底座，没有中英文姓名转换或 Query Rewrite。若知识底座只命中英文姓名，产品页面只会提示用户尝试英文姓名。

## 2. 工作规划

### 阶段 A：稳定性与契约验收

1. 固化学者 Search、Detail、空结果、错误码和 opaque ID 自动化测试。
2. 使用真实环境验证典型英文姓名、中文姓名和不存在姓名。
3. 核对详情中所有可选字段；上游未返回的字段必须隐藏，不显示伪造的零值或占位事实。
4. 验证学者到论文、合作学者的完整导航与返回路径。

### 阶段 B：中文姓名问题定界

1. 对同一学者分别使用中文名、英文名和常见英文变体检索，并记录请求、结果数和首条 ID。
2. 若知识底座可以稳定支持中文名，产品侧不增加 Rewrite。
3. 若知识底座不能支持中文名，先向知识底座组确认正式能力和姓名词典来源。
4. 确需产品侧处理时，在 FastAPI Knowledge Service 的 Query 层实现可测试的 Rewrite；不得放在页面、BFF 或 Integration transport 中，也不得维护无法追溯的硬编码个人名单。

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
- 当前结果：通过。
- 说明：此项验证传输正确，不代表上游能够命中中文姓名。

### A02 学者 Search 和 Detail 契约

- 类型：自动化
- 覆盖：Search/Detail 端点、limit/offset、字段映射、opaque ID、缺省可选数组。
- 命令：同 A01。
- 当前结果：通过。

### A03 空结果与异常映射

- 类型：自动化
- 覆盖：空结果为成功响应；TIMEOUT 可重试；NOT_FOUND 不可重试；非法参数返回 `INVALID_ARGUMENT`。
- 命令：同 A01。
- 当前结果：通过。

### A04 前端状态与跳转

- 类型：自动化
- 覆盖：初始态、loading、zero-result、error、重试入口、论文链接、合作学者链接、opaque ID 路由恢复。
- 命令：`corepack pnpm test`
- 当前结果：通过。

### A05 静态类型与全量回归

- 类型：自动化
- 命令：`corepack pnpm typecheck`、`corepack pnpm test`、`corepack pnpm lint`。
- 当前结果：typecheck 通过；Web 221 项测试全部通过；lint 0 error、2 warning。
- Lint 基线 warning：`features/chat/hooks/use-chat-session.ts` 缺少 `setBusyValue` dependency；`lib/use-popover-placement.ts` 缺少 `anchorRef` dependency，均与学者库无关。

### A06 Backend 全量基线

- 类型：自动化
- 命令：`uv run python -m unittest discover -s tests -v`。
- 当前结果：阻塞于两个与学者库无关的既有问题：`app.services.reading_history` 缺失；Deep Research 报告在 Windows 下使用 CRLF，测试固定断言 LF。
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

## 5. 本轮测试报告

- 学者专项 Backend：17 项通过，0 失败。
- Web 全量测试：221 项通过，0 失败。
- Web TypeScript typecheck：通过。
- Web lint：0 error、2 个与学者库无关的既有 warning。
- Backend 全量：319 项运行，1 失败、1 导入错误、21 跳过；两项失败均不属于学者库。
- 真实知识底座与浏览器人工验收：待执行，重点是中文名/英文名对照、详情字段和跳转。

当前结论：学者库的正式调用链和基础 UI 状态已经成型，可以进入真实环境验收；中文姓名 Query Rewrite 尚未实现，应先用 M02 获得稳定复现证据，再决定由产品 Query 层修复还是反馈知识底座组。
