# M1 Mock 针对性收尾

日期：2026-11-18。保持 `feat/agent-m0-integration` / `acf84bfcfbb939170e563cb5b0a5a03e270555ef`。保留全部既有 M0/M1 修改，无提交、推送、合并、切分支或数据库修补；未调用真实模型。

## 结论与根因

1. **首次挂载 Console Error 未复现、根因未确认，不能宣布已修复。** 启动原有隔离演示，Chrome 新标签直达 `/agents`、刷新、从发现页客户端导航进入，均未捕获该 React Error，读取的 error 级日志为空。检查了 AgentHome/useAgentLauncher、Session 恢复与订阅清理、Composer、AuthProvider、AppShell 及相关布局 Hooks。配置请求在 effect 中启动；Session 订阅有清理及代际校验，没有发现足以证明此警告根因的 render 阶段异步状态写入。未加延迟、额外挂载标记、屏蔽 console 或进行猜测性生命周期改写。现有用例不能稳定覆盖用户最初的触发时序；再次出现时需要保留完整组件栈与触发步骤，不能仅凭警告文字归因于 Next 或 React。
2. **重复是跨 Run 聚合问题，Mock 重试让它稳定暴露。** Control 重试生成三个不同 Run；每个 Runtime 的 turn 都从 1 重新开始，各自产生同一句模拟思考。事件不是同一 SSE ID 被重复投递。前端 StreamState 与 Backend TimelineCapture 原来都只按 turn 划段，未处理 run_start，因而三个片段拼为一个段落。现按 run_start 重置聚合索引，保留此前过程，下一 Run 另起段。没有按字符串去重，也不删除合法执行历史。
3. **dotenv 警告源为 `apps/web/.env.local` 第 26 行。** 使用 dotenv 底层 parser 仅输出文件名/行号与错误布尔分类，未输出任何配置值。启动器为了屏蔽原配置而对该文件调用 Python dotenv_values，触发了与实际取值无关的解析警告。现扫描 assignment 变量名完成屏蔽，不解析这些其他运行时配置的值；专用 M0-C1 验收配置仍用 dotenv_values 正常读取。原 `.env.local`、Backend `.env` 和凭据均未修改。该行自身仍不符合 Python dotenv 语法，其他工具若用 Python 解析原文件仍可能提示；本轮不猜测或重写凭据值。

## 本轮文件

- `apps/backend/app/services/agent_sessions/timeline.py`：run_start 重置局部聚合索引，实时与恢复投影共用。
- `apps/web/features/agent-chat/timeline.ts`：纯函数 startRunStream，保留旧 entries 并重置当前 Run 索引。
- `apps/web/features/agent-chat/shenzhi-ai-page.tsx`：onRunStart 应用边界重置，清当前正文/思考累积。
- `scripts/agent_m1_demo.py`：environment_keys 仅扫描待屏蔽文件的变量名。
- `apps/web/tests/agent/timeline.test.ts`：新增三个 Run 均使用 turn=1 的分段回归，并验证同 Run 增量仍拼接。
- `apps/backend/tests/test_m1_closeout.py`：相同后端分段回归；变量名扫描不解析值/不产生 dotenv warning 的回归。
- 本记录。

## 最终验证

- Web Agent：**54 PASS**，0 FAIL；`tsc -p tsconfig.test.json`、`tsc --noEmit`、三个改动前端文件的 ESLint 均通过。
- Backend：`uv run --no-sync --offline python -m unittest tests.test_m1_closeout tests.test_agent_sessions tests.test_agent_sse_retries tests.test_agent_sse_tail`：**31 PASS**，0 FAIL。
- 实际 BFF → Backend → Agent / 现有 Mock Worker：失败及超时各一个场景通过；持久 Turn process 均为三个独立 reasoning 段，每段只有一次模拟描述，没有三次拼成单段。会话分别为 `ses_8edbf18c22ed4d6fb3bfadc3c22f36af`、`ses_efb7e27ef95145b5bd48766eebf89b1b`。
- 重新启动四服务后未再输出 dotenv 警告，BFF 就绪成功；服务保留用于代码审查后的复核。
- `git diff --check` 通过（本机换行提示不计错误）。

## 剩余风险 / 审查边界

- 首次挂载警告保持**未关闭**；本轮无法稳定复现，不能把“本次未出现”写成“根因已修复”。不建议用猜测性改写掩盖它。
- 已保存的旧 Turn process 若已拼接，不迁移或改写；新执行和重新按事件投影使用 Run 边界。多个 Run 各自真实产生相同描述仍会分别保留，这是执行历史。
- 未新增 Mock 功能，未调整 Agent 核心架构或 UI。真实模型鉴权、费用授权等 M0 外部限制保持原结论。收尾修改现进入代码审查。
