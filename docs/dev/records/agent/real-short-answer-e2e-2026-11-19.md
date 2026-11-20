# 真实短回答端到端验收

日期：2026-11-19。用户在浏览器短回答任务中遇到 `BACKEND_AUTHORIZATION_REJECTED`，随后明确要求修复并完成这次端到端验收。

## 验收结果

场景：原指定账号，在现有产品前端使用默认 `autodl/DeepSeek-V4.1-Flash-1017`、快速模式，提交“只回复：验收通过”。

| 链路 | 结果与证据 |
| --- | --- |
| 浏览器触发 | 点击原会话“重新连接 / 刷新结果”，沿原 Turn/幂等键恢复，没有创建新任务绕过预留 |
| Web/BFF → Backend | 原 Session 恢复并投影为 done，原 Task/Run ID 保持一致 |
| Backend ↔ Agent | 原 pending 绑定恢复为 bound，Grant 生效，执行 Worker 正常领取 |
| Provider → Worker | 一次真实模型调用，回答严格为“验收通过” |
| 用量 → Backend | Usage Projection revision 2，usage_source=provider_usage，usage_status=measured |
| 结算 | prompt 2170、completion 3，合计 2173 Token；Grant closed、settlement_status=settled、overage=false |
| 响应 → 页面 | 浏览器显示“已完成”和回答“验收通过”，截图已保存 |
| 账户余额 | 每日限额 200000，已用 2173，预留 0，剩余 197827 |

会话：`ses_dc31019c3c0840608de83e44b14415a1`。
截图：`apps/agent/workspace/e2e-local-logs/short-answer-result.jpg`。
机器可读结果：同目录 `acceptance-result.json`。本地证据由现有 Git 规则忽略，不包含 API Key。

## 根因与修复

之前修复的 Backend→Agent 配置读取已可用；这次故障发生在反向 Agent→Backend 的授权绑定回调。Agent 进程继承编辑器的代理环境，内部 HTTP 请求没有绕过代理，网络拒绝被包装成 `BACKEND_AUTHORIZATION_REJECTED`。两笔 Submission 已完成原子预留，但 Task 均停在 pending binding，尚无 Call 或 Execution。

为 Agent 本地 env 补充回环地址 NO_PROXY/no_proxy；同步本地及共享任务模板，让四个 Python 启动任务显式追加回环地址并保留原 bypass 配置。更新环境示例和部署说明。没有更改角色密钥、认证门禁、模型调用参数、能力 digest 或 Policy。

核对三个 Agent 进程树身份且确认没有已发模型调用后，重启 Agent API、执行 Worker、Usage Worker，让环境生效。此次三个进程以隐藏窗口运行，日志在 `apps/agent/workspace/e2e-local-logs/`；执行 Worker 和 Usage Worker 正常运行。Web/Backend 未重启。后续切回编辑器任务启动前应先停止这些现有进程，避免重复占用端口或重复启动 Worker。

## 早先失败预留的处理

另一旧验收任务尚未绑定，且经数据库确认没有 Call 和 Execution。通过现有产品 stop 接口将其取消，再通过原 Session 的 resume 接口完成既有幂等绑定恢复；独立 Usage Worker 按原关闭清单协议关闭 Grant，并追加释放账本，释放可证明未用的 100000 Token 预留。旧会话/任务/审计保留，没有直接删除、清零计数器或撤回已发调用。该旧任务没有调用模型。

## 验收边界

本次通过的是一次真实短回答及其 BFF、授权、执行、实测结算和页面显示全链路。没有开展搜索、知识库、长回答、Deep Research 或超额强测；不据此宣布这些功能已验收。model_risk_profile 仍按既有本地显式风险接受策略运行，不代表已有可信 Token 上界证明。

## 后续配置撤回（2026-11-19）

按用户要求，撤回本地 Agent `.env`、Agent/Backend `.env.example` 及本地/共享启动任务中的 `NO_PROXY` / `no_proxy` 配置，并删除部署文档中对应配置要求。用户将关闭本机 Clash 后自行测试。以上验收结果属于当时配置下的历史记录，不代表撤回后已重新验收。本次没有修改 HTTP Client、授权逻辑或启停服务。
