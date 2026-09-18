# Agent 基座精简 + deep-research 可用性：计划与实测证据

> 状态：**计划已确认，A 部分（技能可用性）与 B 部分（基座精简）第一批已执行完毕**，见文末「执行记录」。
> 实测环境：`apps/backend/.venv`（Python 3.12.11），真实 `.env`（DashScope key + Tavily key + 知识库 `http://47.110.47.12`）。
> 证据脚本（临时，未入库）：`.tmp/smoke_kb.py`、`.tmp/probe_kb_raw.py`、`.tmp/probe_kb_fields.py`、`.tmp/probe_kb_cites.py`。

---

## 一、deep-research「效果很差」的实测根因

结论：**不是模型不行，也不是基座循环不行，而是技能声明要用的能力，知识库实际给不出来**——流程必然在 Phase 3/4 空转，靠烧轮次掩盖。

### 证据 1：`citation_graph` 极度稀疏 —— Phase 4（引文追溯）几乎总是空的

**更正（2026-02 实测补充）**：不是"0 条"，而是"**高度稀疏**"。第一次 40 篇里 35 篇成功返回、CITES 0 条；
后续 `scripts/skill_smoke.py --live` 对另一篇论文测得 `citations_available=True, backward=1`。
即：CITES 边**存在但覆盖极低**，对绝大多数论文为空。结论不变——Phase 4 不能在"必然有引文图"的假设上
建模，必须由工具显式声明 `citations_available`，让模型按事实改道。

原始统计（4 组检索词、40 篇论文，逐篇拉 `/api/kg/graph?depth=2`）：

| 关系类型 | 出现情况 |
| --- | --- |
| `HAS_TOPIC` | 每篇 11 条 |
| `AUTHORED_BY` | 1-13 条 |
| `PUBLISHED_IN` / `PART_OF` / `AFFILIATED_WITH` | 各 1-2 条 |
| **`CITES`（backward / forward 的唯一来源）** | **35 篇成功返回中 0 篇；另测单篇为 1 条** |

而 `skills/kb-retrieval/tools.py:89` 只取 `relation == 'CITES'` 的边填 `backward` / `forward`。
实测工具输出：

```json
{"root_id": "paper:2024_naacl_long_347_acl:65f76b302ada",
 "backward": [], "forward": [], "topics": []}
```

上游原始返回实际有 `nodes: 20 / lines: 19`，但全是 `PUBLISHED_IN` / `HAS_TOPIC` / `AUTHORED_BY` / `PART_OF`。
→ 模型拿到的是一个「空得看不出原因」的结果，只能重试、换参数、或干脆跳过并假装做过。

### 证据 2：工具说明与实际能力不符（能力广告造假）

`kb-retrieval/tools.py:75-78` 的工具描述承诺：

> `citation_graph`：按 paper_id 返回引用邻域：backward（它引的奠基文献）、forward（引它的后续文献）、topics（主题标签）。

上游不提供 `CITES`，这三个承诺里只有 `topics` 有数据，而 `topics` 恰恰被实现漏掉了（只从 `backward`/`forward` 派生，`topics` 字段也基于 `kind == 'topic'` 过滤，实测为空）。
模型据此把 Phase 4 当作"该做的事"反复尝试——**说明与实现不一致，是空转的直接来源**。

### 证据 3：错误恢复指引被 `NameError` 掉包（技能承诺的"补搜纪律"完全失效）

`skills/kb-retrieval/tools.py` 用了 `BusinessError`（第 63、83 行）但**没有 import**（该文件只 import 了 json / typing.Any / pydantic / agent.tools / knowledge 等）。
走真实执行路径（`ToolRegistry.dispatch`）实测：

```
===== paper_detail(不存在的 id) =====
[is_error] 工具执行失败: name 'BusinessError' is not defined
===== citation_graph(不存在的 id) =====
[is_error] 工具执行失败: name 'BusinessError' is not defined
```

模型看到的不是"知识库无此 id，请换措辞重查或 scholar_web_search 补搜"，而是 `name 'BusinessError' is not defined` ——
于是 Phase 3 的「detail 失败必须补搜」纪律被彻底绕过，模型只能降级或编造。
（同类检查：`scholar-deep-research/tools.py` 的 import 是正确的，只有 kb-retrieval 缺。）

### 证据 4：交付契约把不可用能力设为硬门槛

`skill-deep-research/SKILL.md` frontmatter：

```yaml
completion:
  tools:
    paper_search: 3
    scholar_web_search: 1
    paper_detail: 5
    citation_graph: 2      # ← 该能力在当前知识库不存在，却要求 ≥2 次
  artifact: {suffixes: [.md], min_chars: 6000}
```

闸门规则是"工具在 `available_tools` 里就要求次数"——`citation_graph` 永远在场、永远为空，
于是契约**必然**逼出 2 次无效调用；闸门还会因为次数不够把已经收工的模型打回，继续烧轮次。

### 证据 5：`paper_search` 的作者字段在上游就是空的（不是我们的映射 bug）

- `/api/retrieval/search` 返回的每条 result 里 `authors` 都是 `[]`（实测原始响应）。
- `/api/kg/paper`（detail）返回的 `authors` 是完整的（实测 6 位作者）。
- 因此只有 `paper_detail` 能提供作者。而 kb-retrieval 正文的引用纪律写的是"作者取工具返回的 authors 字段；
  为空时写（作者未收录）"——模型按纪律执行后，**报告里几乎全部条目标注"（作者未收录）"**，看起来就像效果差。

### 证据 6：上游稳定性与字段缺失（次要但会累积）

- 40 篇里 6 篇 graph 请求 `RemoteProtocolError`（约 15% 瞬时断连）；现有 30s 超时 + 无重试，直接 is_error。
- `paper_detail` 的 `citation_count` / `reference_count` 上游恒为 `null`（adapter 已有注释说明），Phase 2 的"按引用数排序"缺少依据。

### 证据 7：`depth` 参数无效（信息面被锁死）

`depth=1` 与 `depth=2` 返回完全相同的 20 节点 / 19 边。adapter 把 depth 透传给上游，但上游未按 depth 展开。
→ 引文追溯即便有 `CITES`，当前也只能拿到一跳邻域。

### 结论一句话

八阶段流程里，**Phase 1/2（检索、分诊）可用，Phase 3（精读）半可用（作者/DOI/PDF 有，指标没有），
Phase 4（引文追溯）不可用**；而契约与工具说明都假设 Phase 4 可用。模型为满足契约反复调用空工具，
预算被吃在无效动作上，报告质量自然差。

---

## 二、修复计划 A：deep-research 可用性（技能 + 工具，按实测能力对齐）

### A1. 工具层：能力与实现对齐（`skills/kb-retrieval/tools.py`）

1. **补 `from app.core.errors import BusinessError`**（当前 NameError 根因）。
2. `citation_graph` 输出改为"显式能力声明"，把不可用从"空数组"变成"明确事实 + 降级指令"：
   - 有 `CITES` 时：照旧返回 backward / forward；
   - 无 `CITES` 时：返回 `{"citations_available": false, "topics": [...], "note": "该知识库当前不提供引用关系（CITES）。改用 paper_search 检索该文的后续/批评工作，或用 scholar_web_search 查公开页面。"}`；
   - `topics` 修好：从 `HAS_TOPIC` 边/`Topic` 节点取（实测每篇 11 个，是有价值的数据）。
3. `paper_search` 结果补 `authors_note`：authors 为空时显式提示"检索接口不返回作者，需要作者请对该 paper_id 调 paper_detail"，让模型有确定动作，而不是在报告里写"（作者未收录）"。
4. 上游瞬时失败（RemoteProtocolError / 超时）在工具内做**一次**快速重试，减少 15% 的假失败。
5. 统一错误文案为"下一步动作"格式（现状 detail/citation 的文案方向是对的，只是被 NameError 掉包）。

### A2. 技能层：契约与正文按能力对齐（`skills/scholar-deep-research/`）

1. `completion.tools` 删掉 `citation_graph: 2`；改为 `paper_search: 3`、`paper_detail: 5`、`scholar_web_search: 1`（全部实测可用）。
2. Phase 4 正文改写为**条件阶段**："先调一次 `citation_graph` 探测；若返回 `citations_available: false`，
   改为用 `paper_search` 追后续/批评工作，并在报告附录如实记录'该渠道不提供引用关系'——不得假装做过引文追溯，也不得因此放弃对抗性检索。"
3. Phase 3 正文补一句作者口径：作者只从 `paper_detail` 取，`paper_search` 的 authors 为空属预期。
4. `references/quality_assessment.md` / `pitfalls.md`：核对是否还有基于"引用图可用"的检查项（14 问里涉及引文追溯的要按条件阶段改写），并跑一遍引用完整性检查（正文提到的 `references/*.md` 必须真实存在）。

### A3. 闸门层：能力缺失 ≠ 模型失职（`app/services/agent/skills.py`）

`SkillCompletionPolicy._missing` 当前只判断"工具在不在场"。新增一条通用规则：

- 若某工具的最新结果显式声明了 `capability_available: false`（约定字段），则**该契约项不计缺失**，改记一次"能力降级"（可进 `FollowUpContext` 供策略与审计）。
- 这是通用机制，不是为 kb-retrieval 特判：任何技能都能用同一字段声明"这条渠道不可用"，闸门自动让步。

### A4. 可验证性：技能加载冒烟（`scripts/skill_smoke.py`，保留为工具）

把这次的临时探针固化成一条命令：装载全部技能 → 逐个调用其工具的**最小合法参数** → 输出
`工具名 | ok/降级/is_error | 是否声明能力可用 | 首行摘要`。任何技能"说明与实现不符"都会被它一眼看出，
满足"随时可装载一切技能"的可验证性要求。

### A5. 验收口径（三档，供你选）

| 档 | 动作 | 时长/成本 | 能证明什么 |
| --- | --- | --- | --- |
| L1 离线 | 单测 + `skill_smoke.py` | < 1 分钟，零 token | 工具契约、错误文案、闸门让步逻辑正确 |
| L2 半程 live | CLI print 模式跑一个窄问题（如"检索增强生成的长文写作，近三年"），只到 Phase 4，跑完检查 `research_state.json` 与工具调用分布 | 5-10 分钟，约 20-60 万 token | 8 阶段是否真的被走完、Phase 4 是否正确降级 |
| L3 全长 live E2E | 同上但跑完整交付（≥6000 字报告落盘） | 15-30 分钟，约 100-300 万 token | 交付契约、篇幅、引用真实性（人工抽检 [n] ↔ 真实论文） |

L3 才有说服力，但会真实消耗 token 且外部知识库要在线——需要你确认是否跑。

---

## 三、修复计划 B：agent 基座精简（结构性，不改行为）

目标形态：**内核无业务、能力靠装载、装配在一处**。核心包与业务包严格分离，装技能不动内核。

### B1. 删死代码（零风险，直接删）

| 位置 | 内容 | 依据 |
| --- | --- | --- |
| `tools.py:47-49, 56-59, 75-77, 91-97` | `ToolSpec.replay` 及其参数 | 全库只有定义与透传，无任何消费方（设计文档自述"只做元数据标记"） |
| `provider.py:79, 134-135, 139` | `Usage.cache_write_tokens` | 解析后从未被读 |
| `provider.py:106, 402` | `Finish.raw_stop_reason` | 赋值后从未被读（`error_message` 才是被消费的） |
| `json_repair.py:172-181` | `normalized_arguments` | 仅单测引用；wire 兜底已由 `context.wire_arguments` 结构性承担 |
| `service.py:107` | `AGENT_SYSTEM` 基线常量 | 无消费方 |
| `service.py:110-112` | `_tool_gloss` | 单调用点，按 `pi/AGENTS.md` 应内联 |
| `service.py:134-138` | `default_runtime` 包装 | 单调用方，直接构造 `AgentRuntime` |
| `app/api/agent.py` 中未用导入 / `workspace.py:289-291` 的 `__import__('os')` | 风格债 | 顶层 import |

### B2. 内核与中间件解耦（解决"内核 import 技能"这个真正的架构债）

现状：`runtime.py:34` 直接 `from ...skills import Skill, SkillStore, read_skill_tool, SkillPolicy`
—— 设计文档 §3 声称"runtime 的循环执行路径不 import skills"，实际仍有 5 处引用（构造装配 + 策略接线）。

计划：

1. `tools.py` 定义 `ToolPolicy` Protocol（`intercept` / `settle`），`skills.py` 的 `SkillPolicy` 实现它；
   runtime 只持有 `tool_policy: ToolPolicy | None`，不 import skills。
2. 技能相关装配（`read_skill_tool`、`SkillPolicy`、常驻技能正文、`<available_skills>` 清单）收进一个
   `SkillLayer`（skills.py 提供 `build_skill_layer(...)`），service/cli 把它注入 runtime；
   runtime 只认"一个能组装 system 段落、能给策略、能给附加工具"的对象。
3. `__init__.py` 公共出口按"内核 / 能力"两段分区（内核：types/tools/provider/context/runtime/compaction/memory；
   能力：skills/workspace/prompt_templates），避免公共面把中间件混进内核语义。

### B3. `runtime.py` 拆层（747 行 → 主循环 ~450 行 + `tool_batch.py` ~250 行）

`runtime.py` 现在同时承载 5 件事：run 状态、主循环、compaction 编排、工具批执行（并行/顺序两套）、上下文快照构造。计划：

- 新增 `state.py`：`RunState`（现 `_RunState`，去掉下划线，显式字段）+ `_close_pending`（批次闭合）；
- 新增 `tool_batch.py`：`run_tools(...)` 统一入口 + `account` / `record` 记账；
- `runtime.py` 只留：`run` / `resume` / `_drive` / `_run_turn` / `_maybe_compact` + 事件发射。

### B4. 消灭两套工具执行路径的分叉

`_run_tools_sequential`（`:627`）与 `_run_tools_parallel`（`:648`）对 policy 拦截、工具预算、terminal 直出、
latent 启用、记账逻辑各写一遍，`_execute_call`（`:733`）是第三份分派逻辑。
计划：**准备阶段统一**（policy.intercept → 预算 → registry.prepare），执行阶段分两种调度器，
结果回填与终态判定只有一份实现。

### B5. 上下文快照归一：一次遍历

`_stop_context`（`:412`）与 `_follow_up_context`（`:423`）在同一轮里把 messages 反向遍历、找最后一条 assistant、
统计 tool_results——两次。计划：一个 `run_facts(state)` 构造器产出所有事实，`StopContext` / `FollowUpContext`
由它派生（对外字段不变，纯内部去重）。

### B6. 路径禁闭归一

"resolve 后必须仍在根内"现在有 4 处近似实现：`workspace.resolve`、`skills.read_file`、
`SkillCompletionPolicy._artifact`、`write_workspace_file`/`read_session_file`。
计划：`tools.py`（或单独 `paths.py`）提供 `confine(root, path) -> Path`，全部改调它。

### B7. 目录与装配去耦（解决 cli 依赖 service 的问题）

现状：`cli.py` 依赖 `service.py`，而 `service.py` 是容器装配根（import 了 `document_parser`、
`model_provider`、`sessions.repository`、`web_search`）——跑个本地终端却把整个应用层拖进来。

计划：把**业务策略常量**（`IDENTITY` / `BASE_GUIDELINES` / `SKILL_DOC_POINTER` / `RESEARCH_GUIDELINES` /
`RUN_DEADLINE_S` / `compose_agent_system`）从 `service.py` 提到平级 `policies.py`；
`service.py` 只做运行时装配 + SSE 桥接；`cli.py` 只依赖内核 + `policies.py`。
另外把 `service.py` 里的 `_web_search_tool` 与 `export.py`（导出是展示层，只被 `app/api/agent.py` 用）
移出基座目录（建议 `app/services/agent_ext/` 或 `app/api/` 侧）。

### B8. `compose_agent_system` 的空指针

`SKILL_DOC_POINTER` 无条件追加——没挂技能时也会告诉模型"用 read_skill 读参考文件"，而 `read_skill` 不存在。
计划：仅当技能清单/技能工具在场时追加（与 `BASE_GUIDELINES` 注释里"无技能时不写 read_skill"的原则一致）。

### B9. 技能装载的拓展性（保持"随时可装载一切技能"）

1. 技能根可插拔：`SKILLS_DIR` / `SKILLS_EXTRA_DIRS` 环境变量（现在只硬编码 `skills/` + `skills_vendor/`），
   外部技能包不改代码即可挂载，信任级由 `SkillRoot.executable` 表达。
2. `.env.example` 补 `SKILLS_DIR` / `SKILLS_EXTRA_DIRS` / `SKILLS_VENDOR` 三态说明。
3. `skills.load` 的 `only` 分支现在做了两次过滤（先筛顶层目录再比对名单），合并为一次；
   `sync_skill_scripts` 改为模块内私有（只有 hook 用）。

### B10. 不做的（明确边界，避免"顺手改回去"）

- 不动 `pi` 目录、不动 chat/knowledge 业务服务、不动前端。
- 不引入新依赖（技能脚本自检的依赖已够）。
- 不做 prompt 内容重写之外的算法行为变更（除 A 部分的能力对齐）。
- 不改对外事件协议与 HTTP 契约（`RunResult` 字段、SSE 事件名、`/api/v1/agent/*` 全部保持）。

---

## 四、执行顺序（分 6 步，每步独立可验）

1. **A1 + A2**（技能可用性修复）：kb-retrieval 工具 + scholar SKILL.md 与 references。验收：L1 + L2。
2. **A3 + A4**（闸门让步 + 技能冒烟脚本）。验收：L1。
3. **B1 + B4 + B5 + B6**（删死代码 + 执行路径归一 + 快照归一 + 禁闭归一）。验收：agent 测试全绿。
4. **B2 + B7 + B8**（内核解耦 + cli 去耦 + prompt 条件化）。验收：agent 测试全绿 + import 边界 grep 无 `runtime → skills`。
5. **B3**（runtime 拆层）。验收：agent 测试全绿（这是纯搬移，测试必须一行不改全过）。
6. **B9 + 文档更新**（技能根可插拔 + `docs/agent/README.md` §3/§10.7/§15 与 `apps/backend/.env.example` 同步）。
   验收：L1 + 文档与代码一致。
7. 最后：**L3 live E2E**（需要你确认）。验收：报告落盘 ≥6000 字、`research_state.json` 有各阶段记账、
   工具调用分布符合新契约、Phase 4 如实降级、抽检 [n] 与真实论文对应。

---

## 五、当前验证环境的一个坑（会影响验收）

`apps/backend/tests` 大量使用 `tempfile.TemporaryDirectory`；在 DSH 的 `workspace-write` 沙箱下，
`%TEMP%`（`C:\Users\...\AppData\Local\Temp\dsh-*`）不可写/不可清理，导致 150 个用例里 65 个在 setUp 就
`PermissionError`（与代码无关）。基线跑法：

```powershell
cd apps/backend
$env:TEMP = "$PWD\.tmp"; $env:TMP = $env:TEMP    # 仍需允许在该目录写文件
.\.venv\Scripts\python.exe -m unittest tests.test_agent tests.test_agent_skills tests.test_agent_memory tests.test_agent_workspace tests.test_agent_api tests.test_edit_fuzzy
```

另有一个**先于本次改动就存在**的失败需要单独确认是否为环境问题：
`ProviderTests.test_thinking_dropped_on_400_before_outer_retry`（本次基线里 FAIL）。

---

## 六、执行记录（本轮已落地）

### A 部分：deep-research 可用性（已全部完成）

| 改动 | 文件 |
| --- | --- |
| 补 `BusinessError` 导入（NameError 根因）、上游瞬时失败重试一次 | `skills/kb-retrieval/tools.py` |
| `citation_graph` 显式声明 `citations_available` + 降级指令 + 修好 `topics` + `ToolOutput.unavailable` | 同上 |
| `paper_search` 补 `authors_note`（作者只从 detail 取） | 同上 |
| 契约去掉不可用的 `citation_graph`；Phase 2/3/4/6/7 按真实能力改写 | `skills/scholar-deep-research/SKILL.md` |
| 三个 references 重写为真实工具与真实脚本路径（删掉不存在的 `rank_papers.py`、`build_citation_graph.py`；修正 `first_seen_round`/`state.tensions`/`state.selected`/`ranking.*` 等不存在的字段） | `skills/scholar-deep-research/references/*.md` |
| 闸门让步：能力不可用不要求、`read_skill(complete=true)` 显式声明完成后不再打回 | `app/services/agent/skills.py` |
| 能力信号贯穿：`ToolOutput.unavailable` → `ToolResult.unavailable` → run 记账 → `FollowUpContext` | `tools.py` / `types.py` / `runtime.py` |
| 400 降级顺序修正（先摘 `enable_thinking`） | `provider.py` |
| 技能装载自检工具 | `apps/backend/scripts/skill_smoke.py` |

### B 部分：基座精简（B1/B2/B5 部分/B7/B8 已完成）

- **删死代码**：`ToolSpec.replay`、`Usage.cache_write_tokens`、`Finish.raw_stop_reason`、`json_repair.normalized_arguments`、`AGENT_SYSTEM`（并删掉对应陈旧用例）。
- **内核解耦**：`tools.ToolPolicy` 协议 + `skill_tools` / `tool_policy` / `compose_system` 三个注入点；`runtime.py` 模块级不再 import 技能层（仅保留便利回退的惰性导入）。已用 AST 检查确认。
- **策略归位**：新增 `policies.py`（IDENTITY / BASE_GUIDELINES / SKILL_DOC_POINTER / RESEARCH_GUIDELINES / RUN_DEADLINE_S / compose_agent_system）；`cli.py` 不再依赖 `service.py`（本地终端不再拖入 document_parser/sessions/web_search）。
- **prompt 空指修复**：`SKILL_DOC_POINTER` 只在 `read_skill` 实际挂载时出现。

### 验证状态

- `156` 个用例全绿（`test_agent` / `test_agent_skills` / `test_agent_memory` / `test_agent_workspace` / `test_agent_api` / `test_edit_fuzzy` / `test_research_state`）。
- 新增回归：能力不可用声明、`complete=true` 放行、kb 工具坏 id 带补搜指引、无 CITES 时的降级声明。
- `scripts/skill_smoke.py`（离线 + `--live`）通过：17 技能装载、引用完整、契约工具齐备、在线工具可用。
- 顺带修掉的既有环境缺陷：`test_thinking_dropped_on_400_before_outer_retry`（降级顺序）、`test_research_state`（subprocess 未指定 utf-8，Windows GBK 假失败）。

### 未做（下一轮，属于结构性大改，不影响可用性）

B3 `runtime.py` 拆层（747 行 → 主循环 + `tool_batch.py`）、B6 路径禁闭归一、B9 技能根可插拔
（`SKILLS_DIR` / `SKILLS_EXTRA_DIRS`）+ 文档 §3/§10.7/§15 同步。

