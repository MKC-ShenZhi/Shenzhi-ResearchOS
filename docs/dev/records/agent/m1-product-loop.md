# M1 核心科研 Agent 产品闭环执行报告

日期：2026-11-18。结论：**最短产品路径在受控 Mock 执行下通过；真实科研执行验收仍受 M0 上游阻塞，不能标为真实模型 PASS。**

用户可在浏览器创建会话、提交问题、查看过程与报告，并在刷新、切换会话和服务重启后恢复结果。Web/BFF、Backend、Agent API/Control、PostgreSQL、SSE 和 Workspace 为实际服务；替换的是显式启动的 Mock Worker Runtime。没有付费模型、搜索或 Knowledge 业务调用。

## 1. 基线与范围

- 开始及结束分支均为 `feat/agent-m0-integration`，HEAD 均为 `acf84bfcfbb939170e563cb5b0a5a03e270555ef`。
- 初始工作区仅有未跟踪的 `docs/dev/records/agent/m0-c-2-real-task-preflight.md`；该文件原样保留，本轮未写入。
- 没有 Commit、Push、Merge、Rebase、切分支、创建 Worktree、修改 remote 或个人 Cursor 配置。
- 阅读仓库/Web/Backend AGENTS、相关工程说明、Session 持久化、共享契约及实际代码；未重复审计 M0 数据库/Control 架构。
- 复用 M0-C1 的本机隔离 PostgreSQL 双库；容器只读健康检查为 healthy。没有初始化、迁移、清理或修改生产数据库，没有新增依赖或改变锁文件。

## 2. 六环节现状

| 环节 | 检查时的实际情况 | 本轮完成情况与证据 |
| --- | --- | --- |
| 创建/选择 Session | 已实现并有 API/前端测试，尚无本轮浏览器业务证据；M0 只证明空 Session 持久化 | 浏览器匿名身份创建两个会话，侧栏切换成功；BFF owner 隔离与 SQL 读取通过 |
| 输入问题、选择模式、提交 | 已实现并有测试，包括一次性 launch 与幂等键；未完成浏览器联调 | 浏览器深度模式提交、同 Session 追问通过；失败场景提交通过；沿用现有快速/深度 UI 与任务参数 |
| Turn → Task/Run → SSE | 已实现并有 Gateway/契约/事件恢复测试；真实任务受模型阻塞 | 实际跨进程链路使用 Mock Runtime 执行，写入真实隔离双库；首次断订阅后 GET 续接、同键重试不新增 Turn、唯一 result 通过 |
| 实时过程展示 | 已有 Timeline 与事件分发测试；流未返回 result 的 EOF 与闲置超时处理缺失 | 增加明确轮次状态、EOF 错误、45 秒无数据提示、恢复按钮；浏览器显示运行中与过程卡、刷新后续接；传输异常有可执行测试 |
| 成功报告/失败说明 | 已有报告 UI、导出与终态数据结构；实时正文可能覆盖服务端权威结果；没有本轮真实报告 | 最终正文使用 final_text；Mock 报告全文、工具过程、错误文字浏览器通过。成功/超时/停止联调与数据库一致；报告与 Workspace 文件逐字节一致 |
| 刷新/切换/重新进入 | 已实现并有持久化与恢复测试；没有带结果的浏览器证据 | 浏览器执行中刷新、跨会话切换、同 Session 两轮历史恢复通过；四服务重启后原 URL 恢复两轮报告，SQL 确认均 done 且标记 Mock |

没有将页面存在或 Mock 通过解释为真实模型可用。核心路径没有仅靠浏览器本地假数据的环节；真实执行依赖仍单独列于第 7 节。

## 3. 实际修改文件与设计

| 文件 | 变更 |
| --- | --- |
| `apps/web/clients/backend/agent.ts` | SSE 必须收到 result 才算交付完成；EOF 不再静默成功；为 Agent 流设置 45 秒闲置检测 |
| `apps/web/clients/backend/sse.ts` | 可选闲置截止、请求/读取阶段取消与资源清理；保留后端可读错误和 request ID；心跳/任意数据均重置计时 |
| `apps/web/features/agent-chat/shenzhi-ai-page.tsx` | 持久与实时轮次共用状态显示；final_text 为权威正文；连接结果未知时限制新提交，保留同键重试；手动重新 GET/续接；切换时清除旧报告弹层与引用草稿 |
| `apps/web/features/agent-chat/agent-home-page.tsx` | 根据服务端 demo/m1 模型目录显示明确 Mock 提示 |
| `apps/web/tests/agent/stream-failures.test.ts` | EOF、可读错误/request ID、闲置超时、失败与超时 result 的行为测试 |
| `apps/agent/src/agent_app/worker/host.py` | 小范围 Runtime factory 注入；事件持久化、Worker 租约、控制、报告继续复用原实现；Mock 环境拒绝普通模型 Worker |
| `apps/agent/src/agent_app/demo_worker.py` | 独立显式入口，限制 demo/m1，生成带标记的模拟事件/成功报告/失败/超时；支持现有 steer/stop；每份报告独立相对路径，不覆盖旧轮报告 |
| `apps/agent/src/agent_app/api/routes.py` | AGENT_DEMO_MODE=1 时返回符合既有 AgentConfigWire 的 Mock 目录，不读取模型 Provider 目录 |
| `apps/agent/tests/unit/test_demo_worker.py` | Mock 配置 Wire、结果/文件一致、多轮报告保留、失败/超时/取消、真实 Worker 误启拒绝 |
| `apps/agent/.env.example` | 关闭为默认的演示变量及入口说明 |
| `scripts/agent_m1_demo.py` | 四服务启动与有界清理；严格验收库目标检查、非 Mock 队列检查、原配置屏蔽、loopback 绑定、端口占用拒绝、BFF 就绪检查 |
| `scripts/agent_m1_smoke.py` | 从 Web BFF 进入的可重复受控执行验收及只读 SQL 对比，不种子写库、不删除测试记录 |
| `docs/agent/local-demo.md` | 产品负责人可执行启动、身份、问题、预期界面、失败/超时/断线、历史与真实服务切换说明 |
| `docs/agent/session-persistence.md` / `development.md` | 同步当前连接/结果行为及独立 Mock Worker 开发约定 |
| 本记录 | 本轮证据、限制与交付说明 |

未改变公共 Wire Schema、数据模型、服务所有权或 Next/FastAPI 边界。没有新增 Attempt、Checkpoint、高级自动科研状态机或平行执行架构。

## 4. 自动化与检查

| 检查 | 最终结果 |
| --- | --- |
| Web Agent 定向测试 | 53 PASS / 0 FAIL / 0 SKIP，其中新增传输行为测试 4 项；既有测试部分为源代码约束，不将其等同浏览器测试 |
| Web tsc --noEmit | PASS |
| 改动前端文件 ESLint | PASS |
| Backend Session/API/SSE 定向测试 | 41 PASS / 0 FAIL / 0 SKIP；使用现有内存/Gateway fixture，不计为真实模型执行 |
| Agent Demo/Worker/Config 定向测试 | 16 PASS / 0 FAIL / 0 SKIP；使用现有离线 fixture，其中新增 Demo 测试 4 项 |
| Web → BFF → Backend → Agent / Mock Worker → 双 PostgreSQL 联调 | 成功报告、超时、运行中停止 3 个场景 PASS；均验证断订阅重连、唯一 result、幂等与 SQL 一致，另验证其他 owner 404 |
| Git diff --check | PASS；只有本机 CRLF 提示，无空白错误 |

总计 **110 项定向测试通过，另有 3 个实际 Mock 联调场景**。未运行完整生产构建或全仓测试，未以这些测试宣称真实科研执行成功。

执行命令（对应应用目录）：

```text
apps/web:
pnpm exec tsc -p tsconfig.test.json
node --test .next/test-output/tests/agent/*.test.js
pnpm exec tsc --noEmit
pnpm exec eslint features/agent-chat/shenzhi-ai-page.tsx features/agent-chat/agent-home-page.tsx clients/backend/agent.ts clients/backend/sse.ts tests/agent/stream-failures.test.ts

apps/backend:
uv run --no-sync --offline python -m unittest tests.test_agent_sessions tests.test_agent_api tests.test_agent_sse_tail tests.test_agent_sse_retries
uv run --no-sync --offline python ../../scripts/agent_m1_smoke.py

apps/agent:
uv run --no-sync --offline python -m unittest tests.unit.test_demo_worker tests.unit.test_worker_takeover tests.unit.test_worker_heartbeat tests.unit.test_llm_config_api
```

本机受限工具进程中 uv 默认缓存目录无权限；测试进程改用各自被忽略的 `.venv/uv-cache`，并在允许本地进程/网络的执行环境运行。早期沙箱进程挂起后已停止，未将未完成运行计为 PASS。

QA 过程中发现并修复：Mock 事件函数参数与工具 name 冲突；Windows 文本写入换行导致正文/文件不一致；Turbopack pg junction 冲突（仅演示启动器改用 webpack）；屏蔽原配置后空布尔变量导致 BFF 初始化失败；多轮报告复用文件名覆盖旧文件。停止用例第一次在 Worker 领取前取消，符合队列取消语义但不满足“运行中停止”测试前提；脚本改为等待 meta 事件后取消，最终通过。最终结果以上表为准。

## 5. 实际演示证据

浏览器 Chrome，使用既有匿名身份合法访问，无测试账号或认证绕过：

- 报告会话 `ses_25705a8cb50847709b64ed2a41dba11d`：深度问题、思考与工具卡、执行中刷新续接、查看报告；追问第二轮后执行中切走再切回；四服务重启后再次恢复。最后只读 SQL 确认 2 条 Turn，状态均为 done，两个报告均保留 Mock 标记。
- 失败会话 `ses_a9c2fa1c5082405e93a12b65e942ad8c`：页面明确显示“执行失败”和模拟上游不可用说明；没有冒充正常科研回答。
- 截图：`apps/backend/.venv/m1-demo-logs/report.jpg`、`failure.jpg`（本地忽略附件，不提交二进制）。

最终一次可重复联调证据（`apps/backend/.venv/m1-demo-logs/smoke.json`）：

| 场景 | Session | Run / 持久事件数 | 结果 |
| --- | --- | --- | --- |
| Mock 报告 | `ses_1fb04e8fe8b448ee9b4b212eee5a2d7d` | 1 / 5 | done，报告文件/Report/Turn/SSE 一致 |
| Mock 超时 | `ses_1ed2d4a40e95475ea74bec5050ca9a5f` | 3 / 6 | timeout，只交付一个产品 result |
| 运行中停止 | `ses_df2bfa7259064032b4020d3fc66284ee` | 1 / 2 | stopped，事件与 SQL 一致 |

联调脚本使用独立匿名 Cookie，因此它的会话不会出现在产品负责人当前浏览器的侧栏；浏览器应自行提交示例问题。所有模拟记录均通过正常产品提交、Worker 事件和报告接口写入，没有手工插入伪造报告或修改数据库状态。QA 产生的测试历史保留。

## 6. 产品负责人验收入口

详细步骤见 [本地产品演示](../../../agent/local-demo.md)。最短操作：

```powershell
Set-Location D:\Projects\Shenzhi-ResearchOS\apps\backend
uv run --no-sync --offline python ../../scripts/agent_m1_demo.py
```

打开 `http://127.0.0.1:13000/agents`，无需登录。选“深度”，提交“对比 LoRA 与 QLoRA，生成研究报告”；查看运行中、过程卡与“查看报告”；刷新、切换会话并重新进入，核对结果。失败问题以 `[失败]` 开头；超时问题以 `[超时]` 开头。Mock 和真实服务切换的配置/四进程命令已列于演示说明，**本轮没有运行真实服务切换**。

交付时本地演示服务保留运行，四个服务只绑定 loopback，PostgreSQL 容器与 Workspace 保留。若端口已占用，不重复启动。维护者可在该启动器终端 Ctrl+C 统一停止；数据库不会删除。

## 7. 尚需人工验收、外部依赖与风险

- **M0 真实模型阻塞未解除**：AutoDL 当前有效凭据与生成鉴权、明确付费范围/重试预算仍待授权确认。真实生成、检索、Knowledge 与 Deep Research 来源质量均未验收。本轮模型生成与搜索业务调用为 0。
- **人工操作待验证**：浏览器 DevTools Offline/Online 的物理断网交互、报告下载/打印、合法登录态及匿名历史认领、移动端布局。断流/闲置错误已有可执行客户端测试，SSE 断订阅恢复已有真实服务联调，不能将这些扩大成所有浏览器网络行为通过。
- **恢复范围**：本轮验证运行中页面刷新、切换与完成后的服务重启恢复；没有执行运行中 Backend/Worker 故障接管、跨 Backend 投影租约争用、持久卷故障测试，不重新打开 M0 架构审计。
- **产品约束**：断线后使用显式重新连接，不自动重试新任务；重放从 after=0 重建当前轮，尚未增加客户端游标缓存。任务是否结束以持久结果为准。现有取消由 Worker 心跳观察，可能有约 12 秒延迟。
- **演示约束**：启动器依赖当前机器已建 M0-C1 环境和 venv/node_modules，不是通用安装器。它没有真实模型模式，不允许误连生产库；Mock 文本和表格不能用于科研结论。
- **保留与配额**：沿用现有匿名 Cookie/会话保留、Workspace 清理及用量边界；未实现新 TTL 清理、配额或费用硬上限。QA 早期生成的演示历史也保留，不清库处理。

**交付判定：M1 核心产品 Mock 闭环可以亲自操作验收；真实科研闭环保持 PARTIAL/BLOCKED，等待 M0 的外部条件。** 所有改动保持未提交，供 ChatGPT 与维护者审查。
