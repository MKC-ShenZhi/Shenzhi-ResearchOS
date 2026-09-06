# ShenZhi 工程协作规则

本文件适用于整个仓库。进入包含更具体 `AGENTS.md` 的目录时，同时遵循该目录规则。

## 工作原则

- 修改前先阅读相关代码与 `docs/engineering/` 中的说明，优先沿用现有结构、实现和命名。
- 只处理当前任务需要的内容，不进行无关的大范围重构，不擅自建立平行架构或重复实现已有能力。
- 保持 Next.js 与 FastAPI 的职责边界：Web 层负责页面、交互及框架相关能力，核心业务逻辑与数据处理由 FastAPI 承载。
- 页面保持轻量，业务逻辑放入对应 Feature；后端或外部服务调用通过现有 Service、Client 或 Adapter 边界完成。
- 科研能力和第三方服务不得直接绑定页面；接口尚未确定时，不虚构稳定能力或生产行为。
- 知识底座、Deep Research、Auto Research 等科研能力原则上统一经 ShenZhi FastAPI 接入；前端 `clients/<capability>` 只调用 ShenZhi 自身 BFF / Backend API，不直接连接科研组服务；上游科研接口适配统一放在 `apps/backend/app/integrations/<capability>/`。
- 根据实际复杂度组织代码，不为满足目录形式机械创建没有独立职责的层级、文件或抽象。
- 依赖与工具链沿用仓库现有配置和锁文件；新增依赖前先确认确有必要。
- 完成修改后执行与改动范围相符的检查或测试。架构、公共接口或关键开发方式发生变化时，同步更新相关文档。

若任务要求与现有架构存在明显冲突，先说明冲突及影响，再进行实质性调整。

## Agent 与本地工具约定

- 个人 fork、`origin`/`upstream` 等远程配置属于本机 `.git/config`；**禁止**写入仓库内的 Agent 规则、`AGENTS.md` 或文档，以免误导其他成员的 Agent。
- 未获用户明确要求时，Agent **不得**修改 `git remote`、改写他人的 fork 推送目标，或把个人 Cursor 规范（`.cursor/`）提交入库。
- Git 协作流程以 `docs/engineering/git-conventions.md` 为准；个人 Agent 习惯仅留在本地（可用 `.git/info/exclude` 忽略）。
