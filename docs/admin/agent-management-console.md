# Agent 管理控制台

`#/agent` 默认进入供应商与模型目录，顶部提供模型与供应商、Tools、Skills 三个入口。旧 `#/capabilities` 和 `#/agent/models` 也打开合并后的目录。浏览器使用 Admin 会话调用同源 Backend 管理 API。

- **模型与供应商**按 Provider 分组展示 API 地址、凭据状态和启用状态，每组列出模型的内部 ID、上游 ID 和能力摘要。目录支持统一搜索，点击供应商或模型可查看详情，配置修订从同一区域进入。
- **Tools** 提供可搜索的只读目录，详情显示来源、注册类型、可用条件和参数 Schema。
- **Skills** 提供可搜索的只读目录，详情显示资源清单和完整性。文档预览按资源摘要读取并以纯文本显示。

## Provider / Model 配置

从模型与供应商进入「配置管理」。首次初始化可导入完整部署 Spec，已有配置可基于指定修订编辑。表单支持新增和启停 Provider / Model、修改地址和凭据引用、模型映射、默认用途及模型能力。基于修订编辑时保留原 Tool / Skill 引用和其他配置字段。

先检查依赖并核对预览，再创建不可变修订。正式发布沿用现有隔离验证、审批、目标 Worker 确认与生效核验。需要独立审批时，提交独立审批者签名的证明。配置写入由 Backend 和 Agent 的现有开关共同控制。发布状态和阻塞原因在对应配置操作中查看。

当前 Admin 页面不提供 Worker、Task / Run、告警、运行诊断、准入控制和 Agent 专用审计入口。站点级套餐、用户和操作审计分别由各自页面维护。正式部署、SSH 和凭据注入参见 [Admin 部署说明](../../infra/docker/ADMIN.md)。

## 折叠目录与模型资料

供应商默认收起，点击标题展开模型，搜索时自动展开匹配组。模型标题打开右侧滑入的详情抽屉，供应商使用向下展开动效；原模型详情 URL 继续可访问。详情，显示实际 Registry 的上下文长度、输出上限、工具调用、推理和默认用途。

Admin 展示元数据由 Backend 的 `app/data/model_metadata.json` 按完整内部 Model ID 维护，经受认证的 `GET /api/v1/admin-console/agent/model-metadata/{model_id}` 读取。运行配置继续使用 Agent Registry。元数据字段包含 description、documentation_url、source_url、verified_at、effective_from、valid_until 和 pricing。没有资料的模型显示缺失状态。

pricing 每项包含 label、currency（例如 CNY）、input_min_tokens（不含边界，默认 0）、input_max_tokens（含边界，可为空）、schedule，以及每百万 Token 的 input、cache_read、cache_write、output。多条方案可表达分时和输入长度阶梯。价格必须附带来源和核验时间，valid_until 到期时页面提示重新核验。该文件已录入 AutoDL 三个已配置模型的公开标准价和会员价、OpenLux 五个模型的分渠道 USD 价格。AutoDL 原始价格单位按官网前端除以 1000 换算，OpenLux 按官网页面公式计算各渠道单价。DeepSeek 两个旧 ID 按官方公告标明停用，避免套用新 ID 的价格。context_length_display 保存供应商展示的上下文规格，notes 保存报价条件与迁移说明。官网展示规格不自动修改运行 Registry 的安全上限。展示数据不参与授权、Token 计量或结算。

## 即时刷新官网资料

模型抽屉对已建立对应关系的 AutoDL、OpenLux 模型提供「刷新官网数据」。受认证的 POST /agent/model-metadata/{model_id} 经 Backend Integration 访问固定的供应商公开目录，重新换算价格，校验成功后更新进程内缓存和核验时间。失败时保留旧资料并显示错误。进程重启后以随包 JSON 快照为初值，多进程部署各自持有缓存。刷新适用于官网展示资料，运行配置仍经现有修订流程维护。

价格使用 ¥、$ 和 M Token（10⁶ Token）。主要规格集中展示，下方调用参数与预算仅列温度、思考参数、流式用量参数和各用途输出预算。
