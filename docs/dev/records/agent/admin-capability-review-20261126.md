# Admin 能力配置审查与修复记录

日期为 2026-11-26。审查基于 `chore/docker-compose-infra`、提交 `f04e01a` 加当前未提交工作区。审查范围包括独立 Admin 的全部导航入口，重点核对 Agent 配置、能力目录、健康检查、Worker 生效证据、任务调用、权益关联和操作审计。

## 结论

当前 Admin 已具备内部 Agent 目录查询、运行监管和受控配置发布能力。Provider、Model、Tool、Skill 均有列表及详情，Task / Run 能串联调用、Worker、失败与用量。模型日常管理仍依赖 JSON 候选和部署操作，表单式新增、编辑、停用及凭据轮换交互尚待实现。

本次修复三项审查问题，分别涉及固定 Skill 制品检查、Worker Skill 标识与版本匹配、目录最近检查结果展示。其余能力按当前实现和实际证据评价。生产开放仍受认证适配、真实外部 Provider 与凭据轮换、生产故障恢复演练等条件限制。

## 1. 审查方法和证据范围

- 核对 Admin React 页面、Backend 管理路由与 Service、Agent 内部管理接口、能力目录、健康检查、执行配置和 Worker Reporter。
- 阅读 `docs/engineering/architecture-confirmation.md`、`docs/engineering/deployment.md` 的 Admin 入口约定及现有 Phase 3.2 验收记录。
- 使用隔离 SQLite 管理测试和 Chrome 冒烟验证页面与接口链路。源码构建用于验证 TypeScript 和产物生成。
- 跨容器结算、发布回滚及接管结论引用 [已有跨容器验收记录](phase32-chain-acceptance-20261126.md)，本次未重建镜像或复跑容器验收。
- 开关表描述代码默认值及示例配置。本次未读取本地密钥或将本机正在使用的环境配置作为生产状态证据。

## 2. 页面与能力矩阵

| 入口 | 当前实现 | 写入及实际限制 |
| --- | --- | --- |
| 总览 | 当前导航渲染用户总览，通过已有用户投影提供摘要 | 全局 Agent 运行信息在 Agent 管理内查看 |
| 用户管理 | 用户分页、搜索、套餐筛选、权益分配入口 | 分配走既有权益服务，需写权限和操作记录 |
| 能力管理 | 从 Agent `/internal/v1/config` 读取模型、默认模型和 Skill 简介 | 早期只读接口。页面仍提示 Tool 目录尚未接入，完整目录实际位于 Agent 管理 |
| 套餐管理 | Basic、Pro、Research 预览，Policy 发布包导入、发布、迁移预览 | 发布与分配分别执行，已有用户保持其已分配版本，切换需另行操作 |
| 操作审计 | 既有套餐与权益操作记录 | Agent 检查和配置操作有独立审计入口 |
| Agent 运行总览 | Agent API、Agent / Backend 数据库、工作区、Worker、队列及失败摘要 | 失败来源按局部不可用或未知展示，查询范围有边界 |
| Provider / Model | ID、关系、启用状态、默认用途、能力规格、凭据存在、最近调用证据 | 详情可发起检查。日常表单增删改尚未实现 |
| Tools | 参数 Schema、摘要、来源、组装条件、最近调用、Worker 分布 | 登记与某次 Run 实际可调用分别记录，独立安全检查覆盖有限 |
| Skills | 描述、资源摘要、完整性、文件清单、SKILL.md 预览、激活证据 | references / scripts 以清单展示，执行权限和依赖检查需逐项核对 |
| Task / Run | 用户、任务、Worker、状态、模型和工具筛选，Execution、调用、事件及用量 | 监管页面以查询及诊断为主，未提供通用任务干预工作台 |
| Worker / Fleet | 心跳、实例、Manifest、版本历史、当前 Run 和能力差异 | 静默掉线依据心跳推断，独立超时事件巡检器尚待实现 |
| Agent 管理审计 | 检查、诊断、配置操作的状态、原因、时间和操作者 | 诊断读取另记审计，审计完整性校验失败会拒绝返回 |
| 配置中心 | 不可变候选、版本差异、制品历史、证明验证、审批、发布、回滚、对账、准入暂停 | 默认写入关闭，需外部准备制品与签名证明，Worker 确认实际生效 |

页面依据为 `apps/admin/src/main.tsx`、`features/CapabilitiesPage.tsx`、`PlansPage.tsx` 和 `features/agent/`。管理请求经同源 Backend 管理 API，再由 Backend Integration 调 Agent 内部接口，符合当前独立 Admin 架构边界。

## 3. Provider / Model 配置

Provider 列表和详情展示 ID、协议、Base URL 的 origin、凭据是否存在、配置启用及关联模型。Model 展示内部 ID、上游 ID、Provider、Brand、默认用途、能力规格、配置修订及能力版本。页面不返回模型凭据明文。

普通目录来源是 Agent API 进程的注册表，Worker 生效情况由独立 Manifest 证据提供。多版本运行时，API 目录与特定 Worker 清单可能不同，应结合 Worker、配置修订和实际调用核对。

现有配置编辑流程是填写 JSON Spec、创建不可变候选、提交隔离验证签名证明、审批，再对指定 Worker 发布或回滚。候选内包含 Provider、模型、默认用途及 Tool / Skill 制品引用，凭据使用 Secret Reference。此流程需要维护人员准备制品、环境变量和部署，管理员尚无法在普通模型详情页直接编辑上游 Model ID 或更换 Key。

源码依据为 `management_catalog.py`、`integrations/llm/resolver.py`、`execution/config_profile.py`、`AgentConfigCenter.tsx`。

## 4. 健康检查的实际含义

| 对象或模式 | 检查内容 | 证据边界 |
| --- | --- | --- |
| Provider / Model 静态检查 | 注册配置、启用状态和凭据存在 | 无上游请求，无法证明凭据当前有效 |
| network | HTTPS、受限地址解析、认证及模型列表响应 | 使用专用探测 Key。模型检查核对上游 ID 是否在列表中 |
| completion | 固定短提示词及最小完成响应 | 输入输出受限，无法代表复杂任务表现 |
| streaming | SSE 增量与结束帧 | 需要声明支持 Streaming |
| tool_calling | 固定 probe_echo 工具调用返回 | 核对协议响应，未执行真实业务工具 |
| read_file | 工具登记、Schema 及工作区可读 | 读取依赖通过仍需结合实际任务 |
| 写文件、编辑、图表等 | 可检查的工作区依赖 | 缺少安全独立检查时返回 unsupported |
| 知识工具 | Backend 配置、服务凭据存在及健康接口 | 上游科研服务实际检索状态保留 unknown |
| web_search 等其他工具 | 当前无独立安全探测实现 | 返回 unsupported，实际执行事实在 Run 查看 |
| Skill | 元数据、资源路径、digest、声明文件、Python 包依赖和 Worker 版本 | 缺少声明或 Worker 证据时相应步骤为 unknown，结果应结合步骤阅读 |

探测限制包含独立凭据、固定请求、响应大小限制、短超时和并发限制。检查结果有效期为五分钟，管理审计另有每日预算与速率限制。在线检查使用 `AGENT_HEALTHCHECK_PROVIDER_KEYS`，该 Key 需与运行凭据不同。因此在线探测通过所证明的是专用探测凭据与协议链路，运行 Key 的有效性仍需实际调用或独立轮换验收确认。

本次列表列名调整为“最近检查”，展示检查类型、时间、结果和过期状态。该列每个当前页条目读取一条最近审计记录，审计不可用时明确提示，详情保留步骤及历史。此实现增加每页按条目查询的请求量，当前分页规模下使用现有接口，尚无批量检查摘要接口。

源码依据为 `management_checks.py`、Backend `agent_management_audit.py` 和 Admin `AgentDiagnostics.tsx`。

## 5. Tools / Skills 与实际执行

Tool 目录来源于现有工厂的声明及历史调用，包含 base、conditional 和 observed_only 等登记状态。工作区、运行模式、非空 Skill 库等条件影响工具装配。实际 Run 的工具集合由 Worker 上报与调用事实补充。

Skill 展示 discovered、loaded、activated、executable 和依赖状态。`executable` 对应第一方工具工厂的装载许可。固定配置 Skill 制品按不可执行工厂方式加载，vendor 工厂同样受限。通用脚本执行仍依赖运行时的 shell / sandbox 约束，页面资源清单和检查通过本身不足以证明脚本执行成功。

本次针对固定制品与旧目录两种装载路径进行兼容，Skill 资源检查使用已验证制品位置。Worker 裸名称对应资源 digest，`skill:<name>` 对应 SkillIdentity digest，检查按上报格式分别核对，错误版本仍返回 mismatch。

## 6. 运行、用量和 Worker 监管

Task 查询默认近 24 小时，最长时间窗口受后端限制。支持 Task、Run、用户、Worker、执行状态和实际模型 / 工具调用筛选。Run 展示 Execution 历史、调用状态、能力版本、用量及事件元数据，Execution 详情有截断提示。

Agent 观测用量和 Backend 入账分别展示。Backend 核验 Task、Owner、Metering Profile 和提交绑定后读取投影与账本，缺乏可靠绑定时返回未知。中断后未知用量保留对账状态，已有跨容器记录覆盖重复投递去重和正常 Grant 结算。

Worker 通过专用凭据、实例 ID、上报序号及 Manifest 摘要提供证据。重启实例与历史 Manifest 可查询。静默超时仍由最后心跳派生，恢复上报时可记录超时及恢复历史。当前未提供独立静默超时事件巡检和通知闭环。

## 7. 发布、权益与部署开关

| 配置项 | 代码默认 / 示例 | 控制内容 |
| --- | --- | --- |
| `ADMIN_AGENT_CONFIG_WRITE_ENABLED` | false | Backend 配置写入口 |
| `AGENT_CONFIG_WRITE_ENABLED` | false | Agent 配置写入口 |
| `AGENT_CONFIG_ADMISSION_PREFLIGHT` | false | Backend 提交前配置准入检查 |
| `AGENT_CONFIG_SCHEDULING` | off | off / shadow / enforce 调度模式 |
| `ADMIN_AGENT_DIAGNOSTICS` | false | 受限诊断及读取 |
| `AGENT_EXECUTION_CONFIG_FILE` | 按部署配置 | Worker 固定配置制品入口 |
| `ADMIN_AGENT_AUDIT_SECRET` | 需配置 | 独立管理审计签名 |
| `AGENT_CONFIG_MANAGEMENT_TOKEN` | 需配置 | 配置管理专用角色 |

配置写入需要 Backend 和 Agent 两侧允许。审批、CAS 指针、操作 ID、Worker 确认及 fencing 处理用于防止重放或并发切换失序。权益影响检查和持久屏障保护 Policy、Release、Owner 和 Grant 相关变更，Usage Ledger 及结算继续运行。未知网络结果保留待对账状态，Reconciler 能根据原操作回执恢复部分屏障与审计状态，仍需完整故障演练验证生产操作路径。

部署制品由运维侧准备和挂载。Compose 运维脚本默认 Dry Run，实际应用需显式参数。Backend 业务服务无需获得 Docker Socket。页面发布状态应结合 desired revision、active revision 和逐 Worker effective evidence 阅读。

## 8. 认证与审计边界

当前认证仍是 loopback 下的 `local_password` 加签名 Cookie，写请求要求同源控制台请求标识，Cookie 使用 HttpOnly / SameSite。诊断有独立开关，管理凭据、Worker reporter 与配置管理角色分别受控。审计绑定操作者、目标、请求及结果摘要，并校验签名。

正式目标为单管理员 SSH 公钥认证加本地转发。`docs/engineering/deployment.md` 明确 SSH 隧道免密码模式尚待适配，当前实现不能直接作为已完成的生产免密码入口交付。公开反向代理的管理路径阻断及正式隧道验证属于部署验收范围。

## 9. 本次修复与剩余缺口

| 项目 | 处理结果 | 验证方式 |
| --- | --- | --- |
| 固定 Skill 制品误报缺失 | 检查从已验证 Store 获取制品根，再沿用原资源校验 | 制品独立于内置目录的用例通过，资源变化仍拒绝 |
| Skill Worker 证据漏匹配 | 查询兼容裸名称及带前缀 ID，版本按各自格式核对 | 两种 ID 查询、旧 Worker、正确版本及错版本覆盖 |
| 列表健康状态长期未知 | 展示最近审计检查结果、类型、时间及过期状态 | Chrome 页面检查后返回列表核对 |

剩余工作按原始需求的相关程度列出。

1. 模型表单式管理。Provider / Model 的编辑、停用、默认用途调整需要面向管理员的表单及变更预览，可沿用现有候选发布链路。
2. Tool 独立检查覆盖。当前 unsupported / unknown 有明确原因，业务上需进一步确定哪些工具需要可重复执行的探测。
3. 能力管理旧入口。旧页仍使用 v1 配置摘要，Tool 文案与新目录现状不一致，两个入口的信息范围需要统一。
4. Skill 步骤解释。顶层检查 pass 可同时存在未声明依赖等 unknown 步骤，验收应逐项核对，后续可明确完整性评价口径。
5. Worker 静默巡检及通知。当前查询可判断超时，主动事件与通知尚待实现。
6. 真实 Provider、运行凭据轮换、断网恢复和生产并发演练仍待完成。已有替身与隔离数据库证据不能覆盖这些条件。
7. 已有 Phase 3.2 总记录保留较早“跨容器任务未完成”文字，后续补验已写在独立记录中，引用验收结论需同时阅读两份记录。

## 10. 本次验证结果

- `pnpm --dir apps/admin build` 通过，TypeScript 检查及 Vite 产物构建成功。
- 在 `apps/agent` 设置本地 `SHENZHI_TEST_CHROME` 后，使用 `uv run --no-sync python -m pytest -q --tb=short tests/test_management.py tests/test_management_bridge.py tests/test_management_phase2.py tests/test_management_config.py`，31 项全部通过，包含两项 Chrome 浏览器用例。
- 新增回归覆盖制品目录中的 Skill、资源变化、新旧 ID 查询、新旧版本格式，以及错误 Worker 版本拒绝。
- 在浏览器脚本补充“检查通过后回到 Provider 列表，显示通过及 static 类型”的断言后，单独重跑 Phase 2 浏览器用例，1 项通过。
- 本轮测试有两条 Python SQLite 默认 datetime adapter 弃用提示，未发生测试失败。
- 本次修改文件的 `git diff --check` 通过。新增源码文件仍属于现有未提交实现，交付以当前工作区为准。
- 本次验证使用隔离测试数据库和受控 Provider 请求。生产数据库、真实外部 AI、凭据轮换和镜像部署未在本次执行。
