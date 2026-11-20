# M0 综合收尾记录（含 M0-C-2 预检与阻塞证据）

日期：2026-11-18。**自评 PARTIAL，真实任务闭环 BLOCKED，M0 整体仍为 PARTIAL**。仅完成可安全执行的配置、连通性与产品 Session 预检；没有真实 Task/Run 执行，不以这些结果或既有离线测试代替闭环验收。

本记录在本轮 M0 综合收尾中继续更新，不另建阶段。M0-B、M0-R1-A、M0-R1-B、M0-C-1 已由用户确认完成；下文 1–10 保留上一轮实际执行证据，最新 AutoDL 诊断、关闭条件与 M1 依赖见第 11 节。本轮未提交本记录、未新增 Commit，HEAD 保持 `acf84bfcfbb939170e563cb5b0a5a03e270555ef`。

## 1. Git 基线与提交

- 开始分支 `feat/agent-m0-integration`，HEAD `374f4ec7408ca225c29a91c6d9b5b7c617789ab1`，仅有已审查的 M0-C-1 记录待提交，与要求一致。
- 核对内容和差异后，单独提交 `docs/dev/records/agent/m0-c-1-environment-and-databases.md`，Commit：`acf84bfcfbb939170e563cb5b0a5a03e270555ef`。
- 提交信息：`docs(agent): record M0-C-1 environment acceptance`。该 Commit 是本轮当前 HEAD，未 Push、Merge、Rebase、切换分支或创建 Worktree。
- 本轮仅新增本记录，保持未提交；业务代码、测试、迁移和锁文件未改动。

## 2. 复用环境与上游配置

复用 C-1 容器 `m0-c1-postgres-20261118`、卷 `m0-c1-postgres-data-20261118`、两套 venv、根目录 `.env.m0-c1-*` 和专用 Workspace。没有运行初始化脚本，没有重建、删除或清理数据。

必要只读核对 PASS：容器 healthy、卷名正确；Backend 为 `026_home_scheduler_state`，Agent 为 `0002_agent_run_controls`，迁移无偏移。业务表归属正确，独立角色仍不能连接对方数据库，Agent 队列为空。

只将现有 Backend 本地文件中的模型/搜索参数补入专用 Agent 忽略配置，将 Knowledge 参数补入专用 Backend 忽略配置；没有修改原始配置、复制原数据库 URL 或输出秘密。补充脚本检查同名配置差异，不默默覆盖不同值。

| 能力 | 配置 / 检查结果 | 能证明的范围 |
| --- | --- | --- |
| 模型 | 现有 Provider AutoDL，当前默认 `autodl/DeepSeek-V4.1-Flash-1017`；专用 Agent registry 列出 3 个模型 | 仅本地注册与配置解析成功，不代表上游凭据有效或模型可执行 |
| 模型传输 | TCP/TLS PASS | 可建立传输连接，不证明鉴权、生成或配额 |
| 模型只读目录 | 使用已有 Bearer 凭据 GET `/models`；最终默认连接与 `trust_env=False` 直连均为 HTTP 401 | BLOCKED：目录鉴权未通过。不能据此断言所有生成接口均无效，也不能据本地 enabled 判定调用授权有效 |
| Knowledge | `KNOWLEDGE_BASE_API_URL` 已在专用 Backend 配置；TCP PASS | 未执行 Knowledge 检索或 HTTP 业务请求，不证明服务协议或数据可用 |
| 搜索 | `TAVILY_API_KEY` 有值，服务端 TLS PASS；无 SearXNG 配置 | 未调用搜索，凭据、余额与实际检索均未验证 |

初次模型只读目录请求出现 ConnectError；复查得到上述 401。未打印响应正文、凭据或真实上游地址，不使用生成请求进一步探测。全部真实敏感参数仅留在本地忽略文件中。

## 3. 实际服务与执行边界

使用现有 venv 的 Python 启动独立进程，显式加载专用配置：

| 服务 | 实际入口 | 启动器 PID / 结果 |
| --- | --- | --- |
| Agent API | `-m uvicorn agent_app.main:app --host 127.0.0.1 --port 18101` | 24280，health 200 |
| Backend | `-m uvicorn app.main:app --host 127.0.0.1 --port 18000` | 34732，health 200 |
| Backend 重启 | 同上，停止首个 Backend 后再启动 | 30400，health 与相同 Session 重读成功 |
| Worker | 未启动 | NOT RUN，避免在未授权模型环境中触发执行 |

Backend 的 `/api/v1/agent/config` 携专用 BFF 凭据，经真实 HTTP Gateway 调 Agent API，返回 3 个模型并包含 `deep-research` Skill。Skill 列出为 PASS；Runtime 内实际加载并执行该 Skill 为 NOT RUN。

结束后停止本轮服务，按专用端口与进程命令核对无残留。专用 PostgreSQL 仍保留，不删除本轮 Session。日志与脱敏 JSON 证据保存在 Backend `.venv/m0-c2-logs/`、`.venv/m0-c2-preflight.json`、`.venv/m0-c2-services.json`，均为本地忽略文件。

## 4. 最小真实任务：BLOCKED

阻塞一：用户明确要求没有授权不执行付费调用，本轮未获得 Provider 调用次数及金额预算授权。

阻塞二：现有模型凭据的只读目录请求返回 401，上游生成可用性与配额未确认。

因此没有调用 Session run、直接 Task 提交或任何模型生成接口；没有 Task ID、Run ID、Event 或 ExecutionReport 可供真实执行核验。没有向数据库插入伪造执行记录，没有以无凭据失败任务冒充闭环成功。

为验证不触发执行的产品前段，通过正常产品 API 创建并保留了一条明确标注预检用途的 Session：

- 接口：`POST /api/v1/agent/sessions`，使用专用 BFF secret 与随机匿名身份；没有调用 `/sessions/{id}/run`。
- Session ID：`ses_1783ede92d0d4dd895579d77701eb5c9`。
- Owner：`anon:75c80be1-f1c7-4362-9202-9d9babdae532`。
- 产品 GET 重读与只读 SQL 均确认 Session 存在、Turn 数为 0。
- Backend 重启后，同一 GET 的完整 data 响应与重启前一致。

这是**真实 Session 创建与持久化 PASS**，不是题目要求的真实研究任务成功。

## 5. Deep Research

**BLOCKED**：费用授权缺失，模型鉴权未确认，Knowledge 与搜索仅有传输预检。未运行研究、工具检索、Markdown 报告生成或文件读取验收；没有报告路径或报告归属证据。未用 Mock 替代。现有 Workspace 保留，没有伪造产物。

## 6. Task / Run / Event / Report 与产品数据

在服务启动前、预检 Session 创建后、Backend 重启后，通过专用角色连接专用 PostgreSQL 执行只读核对：

| 数据 | 实测 | 判定 |
| --- | --- | --- |
| Backend Session | 上述 ID 和 Owner 匹配 | PASS |
| 该 Session 的 Turn | 0 | PASS：符合未提交任务的预检设计；执行投影 NOT RUN |
| Agent agent_tasks / agent_runs / agent_run_events | 均 0 | PASS：未意外提交任务；执行持久化验收 NOT RUN |
| Agent agent_outbox / agent_run_controls | 均 0 | PASS：无意外派发或控制记录 |
| ExecutionReport / 最终执行状态 / Workspace 报告 | 无 | NOT RUN，没有可核验的真实任务结果 |

没有删除预检 Session 或既有记录。重启仅用于空任务条件下的 Session 读取，不属于 Worker 故障注入。

## 7. Session SSE

**NOT RUN（依赖真实任务被阻塞）**：没有 SSE 事件序列，不能确认本轮真实执行的 ID 连续性、run_start、唯一 result、after 边界、断线续接或完成后重建。历史 R1-A/R1-B 测试不计入本轮真实执行证据。

## 8. 实际命令与结果

```text
根目录：
git branch --show-current
git rev-parse HEAD
git status --short
git diff --check
git add -- docs/dev/records/agent/m0-c-1-environment-and-databases.md
git diff --cached --check
git commit -m "docs(agent): record M0-C-1 environment acceptance"
docker inspect m0-c1-postgres-20261118 --format '{{.State.Health.Status}} {{range .Mounts}}{{.Name}}{{end}}'
apps/backend/.venv/Scripts/python.exe apps/backend/.venv/m0_c1_verify.py

apps/agent：
uv run --no-sync python ../backend/.venv/m0_c2_preflight.py
# 执行两次；第二次补充直连对照。仅 TCP/TLS 和只读目录，无生成/搜索。

apps/backend：
uv run --no-sync python .venv/m0_c2_safe_services.py
# 8 项真实服务/Session 检查 PASS；不启动 Worker，不提交 Task。
```

辅助脚本仅放在现有忽略的 `.venv`，不是业务或测试代码修改。服务脚本的 8 项 PASS 为：双服务 health、配置 Gateway/Skill 列表、产品 API 创建 Session、空 Turn 重读、SQL 对照、Backend 重启读取一致、最终空执行库。资源预检与传输检查另外单列，不混入任务成功数量。

测试统计：服务/Session 定向检查 **8 PASS / 0 FAIL / 0 SKIP**；Provider 目录鉴权 **BLOCKED（401）**。没有运行单元/Mock/SQLite 测试，因此本轮这类测试数量为 0，不沿用 C-1 的 82 PASS。真实任务、研究、SSE 均 NOT RUN / BLOCKED，如上文区分。

## 9. 费用与后续调用计划

- 本轮模型生成 0 次，搜索业务调用 0 次；只执行传输握手和 Provider 只读模型目录 GET，没有发出推理或检索计费用量请求，未查询账单。
- 当前获授权的付费预算为 **0（尚未授权）**，不是代码配置了可执行的货币硬上限。
- 若后续获准继续，拟优先复用现有 AutoDL Flash 模型，最小任务计划为 1 条 fast Session Run，提示要求只给极短回答、不检索；名义预期 1 次逻辑生成。该计划尚未执行，不能保证提示词能限制实际调用次数。
- 当前 Control 对失败/超时可创建最多 3 个 Run，Provider 还有传输重试，Runtime 可能多轮调用。产品 Session run Schema 不暴露货币预算；Worker 对不可强制的 max_model_tokens 预算会明确拒绝。不能把“单任务”写成“只有一次计费”或声称已有金额硬上限。
- 具体人民币预算上限、重试覆盖范围和配额须由用户明确授权并确认可用 Provider 凭据；当前未核实价格，不虚构预计金额。Deep Research 的调用/搜索预算需另行确认，不自动包含在最小任务计划内。

## 10. 结论与停止状态

| 分类 | 结果 |
| --- | --- |
| PASS | 既有专用环境/迁移复核；配置补充；TCP/TLS；真实 Gateway/Skill 列表；正常 API Session 创建、SQL 核对和 Backend 重启持久性 |
| BLOCKED | Provider 只读目录鉴权 401；缺少明确付费调用授权；真实任务与 Deep Research 无法执行 |
| NOT RUN | Worker/Runtime 执行、Task/Run/Event/Report 闭环、报告归属与 Workspace 一致性、真实 SSE/after/续接、付费模型和搜索、Knowledge 业务检索、复杂故障测试 |
| FAIL | 本轮未发现已实际执行的产品预检违反预期；外部目录 401 已明确列为阻塞，不作为成功 |

M0-C-2 自评 **PARTIAL**，不能判定真实任务闭环 PASS。后续需先解决上游鉴权/可用性并取得明确费用授权，然后使用同一专用环境执行正常 Session run，不删除预检记录。本轮在此停止，不自动进入故障接管、多 Run 注入或代码修复。将本记录保持未提交供 ChatGPT 独立审查。

## 11. M0 综合收尾复核与关闭建议（最新）

### 基线与边界

本轮开始核对分支、HEAD、工作区，与用户要求一致；仅本记录未提交。保留了原有记录内容，仅增加本轮结论。没有启动 Worker、提交 Task、调用模型/搜索、写数据库、重新初始化环境、修改原配置或业务代码。没有 Push、Commit、Merge、Rebase、切分支或创建 Worktree。专用容器、卷和 Workspace 原样保留。

### AutoDL 401：诊断结论

1. **路径与协议匹配**：当前 catalog/resolver 给出的 base 与官方 Chat Completions base 相同，Adapter 在其后拼接 `/chat/completions`；目录检查使用同 base 的 `/models`。URL 没有 userinfo/query，不存在把完整 completions URL 再拼接一次的配置错误。代码使用 `Authorization: Bearer <key>`，与 [AutoDL 官方模型调用示例](https://autodl.art/docs/GLM-5.1/) 一致。
2. **令牌类型不能混用**：官方模型示例要求大模型令牌；[应用实例 API](https://autodl.art/docs/app_api/) 使用另一种开发者 Token 及不同鉴权形式。当前文件名 AUTODL_API_KEY 不能证明其来源；不尝试改成裸 Token 或轮流试不同 Header。
3. **配置加载正确**：对原 Backend、专用 Agent、原 Agent、Web 本地文件及当前进程仅检查 Provider key 存在性。只有原 Backend 与专用 Agent 配置了 AutoDL；其他内置 Provider 的 Key 均缺失，当前进程也没有补充 Provider Key。专用 Key 与原 Key 完全相同；没有 Bearer 前缀、内部空白或额外引号，自定义 registry 未配置。
4. **实际启动方式复核**：用 `uv run --no-sync --env-file ../../.env.m0-c1-agent python -c ...` 执行 Agent resolver，确认加载专用数据库变量、解析 Key 与原配置一致、Provider 为 autodl、公开 Agent 模型数为 3。此操作只验证环境读取，不宣称外部鉴权成功。
5. **一次只读请求**：本轮只向已配置模型目录发送一次真实 GET，不跟随重定向、不发送错误 Key、不自动重试。结果 401、无重定向、JSON error message 精确匹配 `Invalid authentication credentials`，没有 permission/scope/forbidden 提示。只输出布尔分类，不输出响应原文、密钥、Token、完整敏感 URL 或其指纹。
6. **目录单独权限尚无证据**：官方已查模型文档没有给出目录特有权限规则；仓库既有 AutoDL 交付记录曾在同一路径取得 200，但那是历史账号/日期证据。当前结果更支持服务端拒绝现有凭据，仍不能仅凭目录 401 断言生成接口一定失败，或区分失效、撤销、过期和令牌类型不匹配。没有通过生成请求验证这些推断。
7. **不能安全自动修复的边界**：本地路由、Header 和环境加载没有发现明确产品缺陷；没有可直接切换的其他已配置 Provider。需要凭据持有人核对令牌所属服务、有效期和权限，必要时仅更新专用忽略配置。不能靠切换高成本型号或修改 Adapter 掩盖鉴权问题。

仓库说明引用的探测脚本实际位于 `apps/backend/scripts/autodl_probe.py`；其 `--list-only` 也是同路径、同 Bearer 的目录检查。本轮通过本地辅助脚本完成一次等价只读检查，没有运行包含生成/工具调用的探测模式。原 Backend `.env` 仍有第 26 行解析警告，但 AutoDL Key 实际解析与专用配置匹配；不将该警告臆断为 401 根因。

### 本轮实际命令与结果

```text
git branch --show-current
git rev-parse HEAD
git status --short
git diff --check
# 只读检查 Provider Adapter、catalog、resolver、实际探测脚本及既有交付记录

# apps/agent，辅助脚本位于 Backend 已忽略的 .venv：
uv run --no-sync python ../backend/.venv/m0_close_diagnose.py
# 仅一次 GET /models；结果为 401，布尔配置诊断见上文
uv run --no-sync --env-file ../../.env.m0-c1-agent python -c "..."
# 只读 resolver 复核：专用环境已加载、Key 匹配、autodl、3 个 Agent 模型
```

第二条 Python 配置核对的实际内容为：读取原本地文件、调用 `load_registry().resolve_model(None, 'agent')`，只打印数据库变量存在性、Key 相等性、Provider ID 和公开模型数量；不发网络请求。辅助脚本与布尔 JSON 存在 `apps/backend/.venv/m0_close_diagnose.py`、`m0-close-diagnose.json`，不进入业务代码。

本轮没有业务代码修复，因此没有重复执行已通过的全量离线测试，新增单元测试数为 0。配置检查 PASS；目录只读鉴权 BLOCKED（401）。第 8 节的 8 项真实服务/Session PASS 是上一轮证据，本轮不重计。生成 0 次、搜索业务调用 0 次、付费授权仍未提供，不存在本轮真实研究报告或执行链路成功证据。

### 已完成工程能力与 M0 关闭条件

| 能力 / 关闭条件 | 当前证据与结论 |
| --- | --- |
| Agent 架构与接口集成 | M0-B 代码级验收完成；Backend/Agent 数据库及服务边界已落地 |
| SSE 尾部与 Worker 事件序号 | M0-R1-A 代码级验收完成；不把离线/SQLite 证据写成真实故障恢复通过 |
| 多 Run Session SSE 游标重建 | M0-R1-B 独立代码审查通过；历史完整枚举和 next-offset 语义已实现 |
| 双库、迁移、基础服务、Gateway | M0-C-1 已独立验收；真实 PostgreSQL、隔离角色与持久卷证据见其记录 |
| Session 产品 API 与重启持久性 | 上一轮真实 API 创建及 SQL/重启重读 PASS；仅有无 Turn 的预检 Session |
| 可用且经授权的真实模型 | BLOCKED：现有目录鉴权失败，没有替代已配置 Provider，费用授权缺失 |
| Task→Run→Worker→Event→Report→Turn→唯一 SSE result | BLOCKED，未执行真实任务；不能关闭此必需缺口 |
| 正常断线续接、完成后重建读取 | NOT RUN，依赖真实任务；不能以离线 R1-B 测试替代 |
| 受控 Deep Research 报告与归属 | BLOCKED；模型/搜索授权和上游业务能力未完成，Workspace/Report/Turn 一致性未实测 |

不新增破坏性故障注入或下一阶段功能作为额外关闭条件，也不因外部阻塞扩大 M0 实现范围。仍需在**同一验收环境、同一现有记录**中补齐上述真实任务及科研报告证据，不能仅通过行政性收尾将 PARTIAL 改为 PASS。

### 与 M1 的接口和功能依赖

- M1 可以沿用现有 Web/BFF → Backend Session/Turn → Gateway → Agent Task/Run 入口和共享 agent-contracts；不建立并行 Runtime、科研组直连或新的事件存储。
- 用户可用的科研任务依赖可用 Provider、明确费用授权、Backend Knowledge 与搜索业务可达性、持久 Workspace，以及 Report/Turn/SSE 的真实交付。当前仅握手/配置存在证据不满足这些产品前提。
- SSE 客户端继续把 after 解释为下一条待收 ID，完整收到事件后加一；持久 Run 枚举与产品 SSE 索引不能混用。M1 消费这些接口时仍需保持 Owner 与 Session/Turn/Task/Run 关联，不把本地 config 的 enabled 当成上游可用性保证。
- Attempt、Checkpoint、工具副作用去重、用户调度等未实现能力不在本次收尾新增，也不能作为已有平台保证向 M1 使用方承诺。Worker 从头执行带来的副作用风险仍按既有文档管理。
- 现有接口足以开展 M1 需求/交互设计；真实科研产品执行验收仍受 M0 未闭环项约束。本记录不宣布 M1 运行条件齐备或自动进入 M1 实现。

### 最终关闭建议

**保持 M0 PARTIAL，不建议关闭为 PASS。** 当前没有需要在缺乏真实复现时修改的产品代码，主要剩余阻塞是有效模型凭据与明确付费授权，以及依赖它们的真实任务/科研报告证据。下一次继续只需补充大模型服务有效令牌或一个已注册兼容 Provider 的合法配置，并明确最小任务与受控 Deep Research 的调用/重试及金额边界；无需再审计或重建 C-1 基础设施，也不再拆分新的 M0 子阶段。

本轮在安全可执行工作完成后停止。此综合记录保持未提交，供 ChatGPT 做 M0 最终审查；不以计划、Mock、静态检查或历史结果填补真实执行空白。
