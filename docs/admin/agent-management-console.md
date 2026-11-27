# Agent 只读目录

Admin 提供 Provider、Model、Tool、Skill 的列表与详情，支持目录搜索、排序与分页。旧 `#/capabilities` 映射至目录；既有 Backend `/capabilities` 接口保持兼容。原有用户、套餐、权益、计量及审计流程保持独立。

调用链：Admin → Backend `/api/v1/admin-console/agent/*` → Agent `/internal/v2/management/*` → Agent 模型 Registry、Tool 工厂及 SkillStore。目录内部接口只接受独立的 `AGENT_MANAGEMENT_TOKEN`，不得与 Gateway、Fact Reader、Control、Worker、Service 令牌复用。Backend 和 Agent API 配置相同值；Compose 清空执行 Worker、Usage Worker 与迁移容器中的目录令牌。浏览器只携带管理 Cookie。

| GET 相对路径 | 数据 |
|---|---|
| `/providers`、`/providers/{provider_id}` | Registry 供应商、协议、地址 origin、凭据存在性、启用和配置状态、关联模型 |
| `/models`、`/models/{model_id:path}` | Registry 模型、能力、默认用途、请求参数、配置及能力摘要 |
| `/tools`、`/tools/{tool_id}` | 真实 Tool 工厂的 ID、说明、参数 Schema 与条件 |
| `/skills`、`/skills/{skill_name}` | SkillStore 技能、摘要、资源及完整性 |
| `/skills/{skill_name}/document?resource_digest=...` | 版本匹配的 SKILL.md 文本预览 |
| `/model-metadata/{model_id:path}` | 仅 Backend：随包静态展示资料与参考价格 |

列表接受 `limit`（1–100）、`cursor`、`search`、`order`。游标绑定目录和查询参数；改变查询应重新开始分页。成功响应 no-store。错误、未配置连接和无效上游响应不伪装为空目录。

目录表示 API 进程的配置快照，不代表 Worker 已装载、用户已授权、供应商可达或凭据有效。Tool 列表重用实际工厂且不运行工具、不创建 Runtime、Session 或工作区；工作区文件工具标明条件，保留 `allow_shell=False`。Skill 第一方工具沿用 SkillStore，不建立平行注册表。此处无 Task/Run/Worker 历史观测、健康探测、配置写操作或发布版本模型。

Skill 文档校验内容摘要、路径边界与大小，Admin 用 React 文本节点预览，不解释 HTML。资源仅列出名称/类型/大小，不执行脚本。未通过完整性校验不可预览；版本变化返回 409。

`app/data/model_metadata.json` 是从管理分支带入的静态资料，标记的核验时间来自原快照，本次集成没有重新核验价格。展示资料不参与模型路由、计费或权益决定。官网刷新接口、抓取客户端及进程字典缓存均未引入。资料不保存实际执行端点，Provider 当前地址由环境配置的 Registry 读取。文档链接与价格来源链接保留。

该只读功能无数据库模型或新增迁移。Agent/Backend 保留各自基线迁移；如共享环境已经运行旧管理分支迁移，须先核对版本及 Trigger，不自动 downgrade、stamp 或删除表。

验证：Admin `pnpm build`；Agent `uv run python -m pytest tests/test_management_catalog.py -q`；Backend `uv run python -m unittest tests.test_agent_catalog tests.test_admin_tunnel`。完整浏览器烟测在仓库根运行 `python apps/admin/tests/catalog_integration.py <CHROME_OR_EDGE_EXECUTABLE>`，先构建 Admin 并安装两套 Python 依赖。脚本使用独立随机 loopback 端口和测试身份，验证真实 Registry，结束时清理本次进程。测试代理仅供烟测；生产必须使用专用 Nginx 和 SSH 入口。
