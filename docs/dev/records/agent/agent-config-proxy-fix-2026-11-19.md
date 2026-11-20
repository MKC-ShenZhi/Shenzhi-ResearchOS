# Agent 配置接口 502 修复

日期：2026-11-19。用户在首页智能搜索入口看到“Agent 配置暂时不可用，请稍后重试”，模型列表未加载。

## 定位与修改

本机 Agent `/internal/v1/config` 直接读取返回 200 和三个公开模型；Backend `/api/v1/agent/config` 与 Web 同源 BFF 同时返回 502。修改前后的运行中接口对比确认，Backend 的内部 HTTP Client 继承编辑器/进程代理环境，导致内部请求受 Internet 代理干扰。

在 `apps/backend/app/services/agent_gateway/client.py` 为内部 Agent Client 显式设置 `trust_env=False`，使 Backend 直接连接受控配置的 Agent 服务。保留既有 Bearer 身份验证、超时、自定义测试 Transport 和响应校验。修改不涉及 Agent Python 实现，能力 digest 与已安装 Policy 均不变，也不改变外部模型/搜索/知识库 Client 的代理行为。

## 验证

- 运行中 Agent、Backend、Web BFF 三段配置接口均返回 200，模型数量均为 3。
- 刷新用户现有首页，错误提示消失，模型菜单显示 `DeepSeek V4.1 Flash · AutoDL`，快速/深度模式选项正常显示。
- 新增真实本机 HTTP 回归测试：设置一个必定返回 502 的本机代理，并清空 NO_PROXY；Agent 配置仍直连成功，代理未收到任何请求或服务 Bearer。
- 后端 Agent API、Session、身份、权益及新回归测试合计 41 项通过。
- 没有提交 AI 任务，没有发送模型请求。实际短回答验收仍由用户在前端进行。

修改文件：Backend Agent Client、新增 `tests/test_agent_gateway_transport.py`、工程部署说明及本记录。
