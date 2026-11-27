# Agent Admin 选择性集成验收记录

日期：2026-11-27（Asia/Shanghai）。仅本地集成，未 Push、未合入一级分支。

## Git 与范围

- 独立 Worktree：`D:\Projects\worktrees\agent-admin-integration\Shenzhi-ResearchOS`。
- 分支：`integration/agent-admin`。
- fetch 后基线：`origin/feat/agent-platform` = `7dcf55062fb0a122354740150628466afa692701`。
- 管理源：`origin/feat/admin-update` = `a7aa1852dc8ac0c1b2bf83313de2e8f5580fd258`。
- 共同祖先：`f04e01ac11f95e75f5c29bdfa0e6d4025c94dbc3`。
- 源分支相对共同祖先114个变更文件，与最新一级分支交叉修改24个。逐文件决策见 [完整清单](source-change-inventory.tsv)。
- 采用按依赖选择性移植及重写适配，不做整分支 merge；管理源提交不会全部成为集成分支祖先。原工作区保持 detached HEAD 与原有文件状态，不切换分支、不 stash/reset/clean、不调整 remote。

## 最终保留

Provider/Model/Tool/Skill 只读目录、列表/详情、搜索/排序/分页、配置状态、能力/请求参数、Schema、资源列表及摘要匹配的 SKILL.md 文本预览。运行配置来自 Agent Registry/既有工厂/SkillStore，不新增运行配置存储。API进程配置不能推导Worker状态、健康或用户授权。模型参考价格与文档为源分支静态快照，没有重新核验价格；移除实际执行端点静态存储，只保留文档/报价来源链接。

保留并适配显式 SSH 隧道认证、独立非root Nginx production 镜像和可选 Compose override。普通生产仍禁用Admin，开发仍用原local_password。隧道入口要求真实loopback、入口secret、Host/Origin校验、管理Cookie及原同源写请求保护。稳定审计身份 `ssh-admin:<principal>` 已适配原审计列表和对账，历史local-admin记录不丢失。

## 裁剪

不引入Provider/Model写操作、候选/版本/验证/审批/发布/回滚、配置Artifact和屏障、准入与Worker版本调度、Worker报告/Manifest/Drain/Resume、任务运行观测/干预、探测/诊断/告警、Agent专用操作审计。对应Router、Service、Contracts、Models、迁移、环境变量、CI、部署脚本和测试均未引入。没有用隐藏页面或关闭开关保留后端写链路。

官网主动刷新接口、抓取客户端和进程内缓存未引入。新目录API只有GET；契约仅含目录类型，没有运行/控制/诊断类型。旧Capabilities前端由新目录替代，原Backend `/capabilities` API保持兼容。

## 关键冲突处理

- `api/v2.py` 保持删除。目录路由使用当前 `api/routes.py` 的V2Route/role，只向原角色隔离清单加入独立目录令牌；不恢复V1或旧协议。
- Backend 保持当前 `agent_gateway/gateway.py`、`agent_control.py` 和业务执行链；管理读取经独立只读Integration，`trust_env=False`、响应大小上限、严格响应契约和安全错误映射。
- 不引入管理分支对 composition/control/Runtime/Worker/metering/resolver 的配置发布与调度改动。通过与基线逐路径比对验证这些目录及Gateway/Billing/Message/Web源码未变。
- Admin 主入口基于最新平台保留用户/套餐/审计，替换能力目录；清除配置管理与刷新官网的前端依赖及无用样式。React检查覆盖取消请求、路由重置、文本预览、dialog标题/关闭和并行目录请求。
- 生产override显式设置独立 `ADMIN_TUNNEL_SESSION_SECRET`，覆盖原生产禁用配置中的空Session Secret；迁移和执行/用量Worker不持有目录令牌。管理认证仍由现有core/admin_auth边界负责。

## 数据库

所有一级分支迁移及历史逐字节保留，未新增、重写、downgrade或stamp任何迁移。

- Backend单Head：`030_merge_billing_message`，保留029_billing与029_agent_message及原merge revision。
- Agent单Head：`0003_agent_metering`。
- 源分支Agent0004–0008依赖管理/配置/Worker生命周期，Backend029_agent_management和030_agent_config_barrier依赖专用审计与配置交接，最终只读目录均不需要，因此不引入。
- 独立PostgreSQL16临时库从空库执行两套 `alembic upgrade head` 成功。查询Backend public schema无management/config barrier表、无config barrier Trigger。

**共享环境执行状态未知。** 未连接共享或生产数据库，不能认定源管理迁移从未执行。若有环境已执行这些revision，不能直接对其运行本分支Alembic；先备份并核对alembic_version、管理表、未决交接及Trigger，单独设计迁移衔接。这里没有通过删历史、手工stamp或移除屏障绕过风险。

## 可执行验证与结果

| 位置 | 命令/检查 | 结果 |
|---|---|---|
| apps/agent | `uv run --no-sync python -m pytest tests -q` | 320 passed、60 skipped、137 subtests passed；跳过为原需显式环境的集成测试；有Starlette/SQLite弃用提示，无失败 |
| apps/backend | `uv run --no-sync python -m unittest discover -s tests` | 最终593 tests，OK，98 skipped；跳过为需专用数据库/外部环境的原用例 |
| apps/backend | 设置独立 `BILLING_TEST_DATABASE_URL` / `TEST_AGENT_MESSAGE_DATABASE_URL` 后，`uv run --no-sync python -m unittest tests.test_billing_postgres tests.test_agent_message_postgres` | Billing+Message持久化18 tests通过；追加的隧道/历史身份真实SQL用例单独1 test通过，共19项 |
| apps/backend | `uv run --no-sync python -m unittest tests.test_agent_catalog` | 6 tests通过，覆盖只读路由、静态资料、契约、服务端凭据与错误映射；也纳入完整回归 |
| apps/agent、apps/backend | 各自设置独立测试DSN，`uv run --no-sync alembic upgrade head`、`alembic current`、`alembic heads` | 完整升级成功，各一个Head，无管理迁移 |
| apps/admin | `pnpm build`、`pnpm typecheck` | 最终代码均通过 |
| apps/web | `pnpm test`、`pnpm typecheck` | 491 tests全部通过，类型检查通过；包括公共BFF管理路径阻断及Billing/Message相关测试 |
| 仓库根 | `python apps/admin/tests/catalog_integration.py <CHROME_OR_EDGE_EXECUTABLE>` | 真实Chrome → 独立同源隧道测试入口 → Backend → Agent Registry通过；详情、搜索、Schema和Skill预览正常；无浏览器异常、无Agent令牌、管理目录请求全GET |
| 仓库根 | `docker build -f apps/admin/Dockerfile --target production -t shenzhi/admin:agent-admin-integration .` | 最终生产镜像构建通过，不覆盖现有local标签 |
| infra/docker | `compose.yml + compose.prod.yml + compose.admin.yml --profile admin --profile full config --format json` | 断言Admin production target、独立Session Secret、loopback端口、数据库不发布、Worker/迁移无目录令牌均通过 |
| 独立容器 | 最终Admin生产Nginx镜像 + 当前Backend/Agent源码只读挂载到已有依赖镜像，独立network namespace | 完整Nginx → Backend → Agent：5 Providers、16 Models、13 Tools、1 Skill、文档和静态价格读取通过；Host/Origin/cross-site拒绝通过；Nginx `-t`通过 |
| Git/源码 | `git diff --check`、基线保护路径比对、超范围依赖/变量搜索 | 通过；无旧V1/管理写模块残留；无锁文件和基础迁移变化 |

依赖安装说明：原uv锁文件镜像下载返回403；切换索引配合 `--locked` 会要求更新锁文件，未采用。使用 `uv export --frozen --format requirements-txt --no-emit-project --no-header` 导出原版本与哈希，再 `uv pip sync --python .venv/Scripts/python.exe <export> --index-url https://pypi.org/simple` 安装；Agent另外 `uv pip install --no-deps -e .`。验证用 `uv run --no-sync`，未调整任何依赖与锁文件。导出文件仅临时使用，不交付入库。

浏览器测试首次发现源测试标题仍写“Agent管理”，已适配最终“Agent目录”；独立脚本的Windows venv子进程树清理已完善。真实SQL审计测试精确预期包含已有seed的local-admin:test，不修改筛选标准。浏览器快速切换可能让烟测代理记录客户端取消连接，生产链及页面检查无失败；没有吞异常作为修复。

## 留存与上线边界

- [目录截图](agent-admin-catalog.png)；实际页面、Schema与文档预览已浏览器验收。
- 本次测试容器使用 `shenzhi-agent-admin-integration-*` 独立名称与标签；PostgreSQL使用随机loopback端口和tmpfs，没有持久卷。结束时仅清理本次测试容器，未停止/重建其他任务容器；保留Worktree及集成分支。
- 本地代码范围内具备合入审查条件。未执行Push、正式合并或服务器部署。
- 尚需真实服务器验收SSH密钥/PermitOpen、开关隧道连接、实际公共反向代理及共享环境迁移状态。本次验证了隧道HTTP信任边界和生产Nginx链，未声称已完成远程SSH验收。
- 源价格快照真实性/时效没有重新核验，不参与Billing结算。没有未解决的本次代码测试失败。
