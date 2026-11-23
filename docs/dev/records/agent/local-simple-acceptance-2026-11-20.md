# Agent 本地简单验收与提交整理

日期：2026-11-20。用户确认本轮按“简单验收通过”收尾，整理当前本地内容并提交。此结论不扩大为完整生产验收。

## 当前交付

- Free 默认分配、首次使用补齐和只读用户管理：复用 Better Auth 用户、Backend 权益与现有 BFF 边界。
- Agent 能力快照导出、调用后同步结算和跨任务超额门禁；独立 Usage Worker 继续承担恢复与关闭职责。
- 正式登录的产品调用接入 V2 Gateway，保持幂等键和原 SSE/会话恢复边界。
- 修复 Backend 内部 Agent Client 的代理继承问题，以及论文检索/详情产品 `topics` 与严格 Agent Wire 的不兼容。
- 补齐全栈及三个 Agent 服务的编辑器任务模板、独立数据库迁移入口。

## 本地验收证据与边界

- 真实短回答、Provider usage 和结算闭环见 [短回答验收记录](real-short-answer-e2e-2026-11-19.md)。
- 原论文检索经修复后返回 HTTP 200 和 10 篇论文，见 [检索契约修复记录](paper-search-contract-fix-2026-11-19.md)。
- 两次较长检索任务最后的模型调用被 `QUOTA_EXHAUSTED` 拒绝；界面仍显示笼统的“调用授权或启动未获可信回执”，不记为完整长任务成功。
- 默认 Free 为上海自然日 200,000 Token、每任务预留 100,000、单次模型调用额度上界 16,000；输入与输出均计量，Tool/Skill 不单独收费。该上界不是可信输入 Token 数学证明。本地指定账号的风险接受记录见 [风险配置记录](local-model-risk-profile-2026-11-19.md)。
- 用户要求撤回的 `.env` 与任务 `NO_PROXY/no_proxy` 设置已撤回。此前验收留下的三个隐藏 Agent 进程已清理；后续由用户的编辑器任务启动，本次整理不启停服务。
- 同目录较早的设计、盘点、研发收尾与部署准备记录是各自时间点的快照，其未完成事项应结合后续记录阅读；当前实现约定以 `docs/agent/` 和 `docs/engineering/` 为准。

## 提交前检查

- Agent 持久化、计量边界、能力导出及共享契约：56 passed，19 subtests passed。
- Backend 权益、Agent API、Knowledge 契约、内部 HTTP、身份及会话：43 tests OK。
- 双 PostgreSQL 集成回归：36 passed，使用既有显式选择的两个本机 `shenzhi_a_line_*` 专用测试库及随机隔离 schema，覆盖并发预留、结算、Free 补齐、管理员权限与列表、迁移等；未使用业务库。
- Web：443 tests passed；TypeScript 检查及改动文件 ESLint 通过。Web 测试首次因沙箱禁止连接本地测试 HTTP 服务而失败，在正常本机执行环境重跑通过。
- `git diff --check` 通过；提交候选文件未发现私钥、常见凭据模式或真实 IP 字面值。
- 本地 `.env`、密钥、Policy/能力导出实值、日志、截图、测试库配置和 `.vscode/tasks.json` 保留在现有忽略范围，不纳入提交。

本次只提交到当前工作分支，不推送、不合并、不修改远程配置或本地数据库权益。
