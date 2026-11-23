# TOKEN_BOUND_UNPROVEN 定位与局部修复

## 实际证据

只读数据库查询确认 basic/pro/research-v1-20261120-availability 的 model_risk_profile 均为null，DeepSeek逐模型预算均缺失。实际失败Permit请求为 model:autodl/DeepSeek-V4.1-Flash-1017，risk_profile=null，input_bytes=7411，requested_output_tokens=32768，model_max_output_tokens=32768，model_context_window=null。

全仓库搜索仅 `apps/backend/app/services/agent_entitlements/service.py` 的 `Entitlements.permit` 生成此拒绝原因：main或summary用途且Policy风险引用为空，或请求风险引用与Policy不相等。其他引用为文档和测试断言，无第二个生产触发点。此次两个引用均为null，命中“Policy缺失”分支，不是输出上限缺失或Provider未发送max_tokens。该拒绝早于真实Provider调用。

调用链：Web同源BFF→Backend Session run/AgentGatewayV2提交→Agent Task及Worker claim→Backend授权状态返回风险引用→WorkerMeter将引用写入CallIntent→Control转换CallPermitRequest→Backend Entitlements.permit。动态预算从Provider完整请求测量input_bytes；批准后O通过Permit/start回传，Provider将max_tokens覆盖为O并在发送前核对正文/预算及唯一发送权。

根因是初始正式包就没有风险引用或逐模型预算，上轮 --previous-bundle 原样继承空配置而没有提前提示；不是新身份摘要字段或新增预算比例字段的兼容性故障。DeepSeek注册输出32768、Agent默认32768，实际请求也为32768；上下文声明未知。

## 修改

- 新增 DeepSeek 专用有限预算JSON：输入字节1:1+1024余量，输出最多4096，上下文应用预算32768。该边界不冒称上游真实上下文；max_tokens覆盖思考消耗仍依赖原Provider接入契约，不伪造实测或审批。
- 生成命令遇到缺失风险引用或全部预算为空时提前失败。预算覆盖按模型ID合并，允许只启用DeepSeek，未配置预算的其他模型继续被拒绝，不要求为了修复一个模型而批准全部模型。
- TOKEN_BOUND_UNPROVEN 记录Policy/请求风险引用和模型预算存在性，预算/额度门禁未关闭。
- 离线准备 `apps/backend/workspace/formal-plans-deepseek-budget.json`，沿用现有能力、套餐权限、日配额，只增加DeepSeek预算/风险引用并更新不可变修订身份；该文件在本地workspace，不提交审批或数据库变更。审批字段由现有Admin填写。

以已观察的7411字节请求为例，在余额和其他限制允许时，输入预留8435、输出最多4096、合计最多12531。真实用量按原账本结算；未确认用量保留预留，失败不当零。

## 用户后续操作

重启Backend以载入生成器兼容的发布校验和诊断日志；不需要重新导出能力或重启Agent API/Worker/Usage Worker。现有Admin发布离线包并重新分配新Policy后，使用新一轮消息重新提交；历史被拒绝的Permit不可重放为成功。未关闭的Grant继续由现有Usage Worker恢复/关闭，不直接改库。其他两个模型没有增加预算，继续保持原来的不可调用状态。

本次未运行测试、构建、Lint、类型检查或服务；未请求Provider、修改数据库、执行部署、提交或推送。
