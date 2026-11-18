# M1 本地产品演示

本演示使用真实 Web BFF、Backend Session/Turn、Agent API/Control、PostgreSQL 与产品 SSE；**执行内容来自独立 Mock Worker，不调用真实模型、搜索或 Knowledge，不证明真实科研能力可用**。页面、模型选项、事件警告和报告均标记 Mock。

## 启动与身份

需要已安装的 Web node_modules、Backend/Agent venv，以及 M0-C1 隔离环境。启动器只接受本机 `55432` 的 `shenzhi_m0c1_backend` / `shenzhi_m0c1_agent`，从根目录已有且被 Git 忽略的 `.env.m0-c1-backend` / `.env.m0-c1-agent` 读取数据库凭据。不会迁移、初始化、清库或修改这些配置。发现非 Mock 的 pending/running Run 时拒绝启动。

PowerShell：

```powershell
Set-Location D:\Projects\Shenzhi-ResearchOS
docker inspect m0-c1-postgres-20261118 --format '{{.State.Health.Status}}'
# 若这个既有容器处于 stopped，仅启动它；不要重跑 M0 初始化脚本：
# docker start m0-c1-postgres-20261118
Set-Location apps/backend
uv run --no-sync --offline python ../../scripts/agent_m1_demo.py
```

终端显示“Mock 演示已启动”后打开 [AI 助手](http://127.0.0.1:13000/agents)。启动器同时检查匿名身份 BFF 与 Agent config；端口占用时停止，避免接入其他进程。Ctrl+C 结束此启动器创建的所有子进程；数据库和历史保留。

演示使用产品已有的**匿名浏览器身份**，无需测试账号、密码、验证码或认证绕过。始终使用同一浏览器配置和 `127.0.0.1`，保留 `shenzhi-chat-anon` Cookie（有效期沿用当前产品配置）。切换到 localhost、无痕窗口、其他浏览器或清 Cookie 会得到不同历史。这里没有配置邮箱/OAuth，也没有写认证表；登录态认领验收使用独立的合法认证环境。

四个服务分别为 Web `13000`、Backend `18000`、Agent API `18101` 与 `agent_app.demo_worker`。仅绑定 loopback。Windows 演示使用 Next 的 `--webpack`，避免本机 Turbopack 的 pg junction 冲突；不修改仓库默认开发脚本。日志、自动化 JSON 和截图位于 `apps/backend/.venv/m1-demo-logs/`，Workspace 位于 `apps/agent/workspace/m1-demo/`，均被现有 Git 规则忽略。

Agent API 按 `AGENT_DEMO_MODE` 拒绝混用的提交与 Worker 领取；Worker 领取请求携带 `demo_mode`（默认 false）。Control 的 SQL 领取同时按 `demo/m1` 过滤首次任务和过期租约，正式 Worker 也拒绝执行 Mock 请求。升级时同步重启 API 和 Worker；隔离数据库与启动器检查仍须保留。

## 产品负责人操作表

| 操作 | 预期界面与结果 |
| --- | --- |
| 进入 `/agents` | 显示 Mock 演示说明，模型为“Mock 演示（无模型调用）”；侧栏列出当前浏览器的历史会话 |
| 在模型与选项中选择“快速”，输入“Diffusion Policy 有什么创新？”并发送 | 创建 Session，URL 变成 `?session=...`；出现用户消息、“任务执行中”和过程卡；约 16 秒后显示模拟回答与“已完成” |
| 新建对话，选择“深度”，输入“对比 LoRA 与 QLoRA，生成研究报告” | 显示思考、写文件工具事件，随后出现“查看报告”；全文带 Mock 说明、示意比较表，无伪造文献来源 |
| 展开过程卡、打开报告 | 查看执行事件与 Markdown 全文；报告可使用现有导出 HTML、打印/PDF 功能 |
| 执行中刷新，或切到另一个历史会话后切回来 | 从 Backend 恢复 Session，并重新订阅持久事件；不重新提交任务。完成后刷新仍有结果和报告 |
| 同一会话继续提问 | 新增一条 Turn，之前的消息与报告继续可查看 |
| 新对话输入 `[失败] 验证上游不可用` | 受控失败，沿用既有 Control 重试（最多 3 个 Run，约 12 秒）；最终显示“执行失败”和“Mock 演示：模拟上游服务不可用，请稍后重试” |
| 新对话输入 `[超时] 验证执行时间上限` | 受控超时，既有重试后显示“执行超时”和时间上限说明；刷新仍为该终态 |
| 普通任务运行中点击“停止” | 发送现有取消请求；Worker 随心跳观察取消，最长约 12 秒后显示“已停止”，不把断订阅当作取消 |
| 浏览器开发者工具 Network 切到 Offline，执行中断网 | 网络异常或 45 秒无数据后显示连接错误；不把它当成模型执行失败。恢复 Online 后点击“重新连接 / 刷新结果”，从后端重读/续接；未确认执行状态前禁止新提交 |
| 全部任务完成后 Ctrl+C，重新运行启动命令，再打开原 Session URL | 历史从 PostgreSQL 恢复，报告正文与已保存记录一致 |

这里的“深度”只在 Mock Worker 中触发示意报告。真实 Runtime 中 mode 仍是资源倾向；真实 Deep Research 应使用现有 `deep-research` Skill，不把模式选项描述成新算法能力。

## 可重复自动联调

演示服务保持运行，在另一个终端：

```powershell
Set-Location D:\Projects\Shenzhi-ResearchOS\apps\backend
uv run --no-sync --offline python ../../scripts/agent_m1_smoke.py
```

脚本先确认 BFF 返回的默认模型严格为 `demo/m1`，否则拒绝提交。它创建自己的匿名 Mock 会话，验证报告、超时、手动停止、首次订阅断开后 GET 续接、连续 SSE ID、唯一 result、同键重试不新增 Turn、其他 owner 404，以及 Backend/Agent 双库记录和报告文件一致性。不会删除测试记录。`smoke.json` 是本次结果，不是可替代真实模型验收的证明。

## 切换真实服务

先停止 Mock 启动器并确保演示任务已结束。**不使用演示启动器运行真实模型**；准备经审查、被 Git 忽略的 `.env.m1-real-agent`、`.env.m1-real-backend`、`.env.m1-real-web`，保持隔离数据库，Backend/Agent 服务 Token 一致，Web/Backend BFF secret 一致；真实 API 和 Worker 的 Workspace 相同，且与 Mock Workspace 分开。Agent 设置 `AGENT_DEMO_MODE=0`，配置已有支持的 Provider；Web 指向本机 Backend。

凭据有效、模型/搜索可用及费用范围得到明确授权后，按正常四进程启动（分别在对应目录、独立终端）：

```powershell
# apps/agent
uv run --no-sync --env-file ../../.env.m1-real-agent uvicorn agent_app.main:app --host 127.0.0.1 --port 18101
uv run --no-sync --env-file ../../.env.m1-real-agent python -m agent_app.worker_main
# apps/backend
uv run --no-sync --env-file ../../.env.m1-real-backend uvicorn app.main:app --host 127.0.0.1 --port 18000
# apps/web
node --env-file=../../.env.m1-real-web node_modules/next/dist/bin/next dev --webpack --hostname 127.0.0.1 --port 13000
```

Web 的进程环境优先于 `.env.local`；真实专用 Web 配置须显式设置数据库、BFF、Auth URL/secret 和所需认证开关，不能默默继承原配置。界面从 `/agent/config` 读取真实模型目录，无需改业务代码或前端 Mock 开关。Mock 历史继续保留自身的警告与报告标记。

本轮未启动上述真实配置，未调用付费模型或搜索。AutoDL 鉴权与费用授权仍按 M0 记录保持阻塞，不能以目录 enabled 或 Mock 成功宣布真实执行通过。
