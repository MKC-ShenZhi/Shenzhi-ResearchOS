# ShenZhi Admin Console V1

独立 Vite / React 19 / TypeScript / Tailwind CSS 4 / lucide-react 前端，固定开发端口 3101。无 Web 内部依赖，无独立业务后端。

## 结构与 API

- `src/main.tsx`：登录、会话检查、管理布局与 hash 路由（总览、用户、套餐、审计、Agent 目录）。
- `src/features/`：用户权益、套餐发布、审计与能力目录页面。
- `src/api.ts`、`useResource.ts`：同源 Cookie 请求、错误与可取消加载。
- `src/types.ts`：管理用户 API 类型；统计口径由 Backend Service 维护。
- `vite.config.ts`：开发反向代理；`pnpm-lock.yaml` 独立锁定依赖。

浏览器 → `/api/v1/admin-console/*` → Backend → 用户 Service / Agent 内部配置。
不经过 Web BFF、Better Auth，也不允许浏览器携带 Agent 密钥。

| 方法 | 相对 API 路径 | 认证 |
|---|---|---|
| POST | /auth/login | 本地账号密码 |
| POST | /auth/logout | 管理会话 |
| GET | /auth/me | 管理会话 |
| GET | /users | 管理会话；page/page_size/search/plan_id |
| GET | /capabilities | 管理会话 |

统一 code/data 或 code/message 响应；成功、认证失败、校验失败响应均 no-store。

## 本地配置与启动

Backend `.env` 添加（不要提交真实凭据）：

```env
ADMIN_AUTH_MODE=local_password
ADMIN_LOCAL_USERNAME=admin
ADMIN_LOCAL_PASSWORD=CHANGE_ME
ADMIN_SESSION_SECRET=
ADMIN_SESSION_TTL_SECONDS=28800
ADMIN_AUTH_LOCAL_ONLY=true
AGENT_INTERNAL_URL=<AGENT_INTERNAL_URL>
AGENT_SERVICE_TOKEN=<AGENT_SERVICE_TOKEN>
```

本地测试将密码改为任务指定的 `123456`；使用 `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"` 生成 Session Secret，至少 32 字符。TTL 默认 8 小时，允许范围 1–86400 秒。缺失配置、CHANGE_ME、非 loopback 均拒绝访问。

终端一：

```powershell
cd apps/backend
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --env-file .env --no-proxy-headers
```

终端二：

```powershell
cd apps/admin
pnpm install
pnpm dev --host 127.0.0.1 --port 3101
```

访问 http://127.0.0.1:3101 。Admin `.env.local` 可配置服务端 `ADMIN_BACKEND_ORIGIN`（默认 http://127.0.0.1:8000），没有 VITE_ 前缀，不暴露到浏览器。检查：`pnpm typecheck`、`pnpm build`。Backend：`uv run python -m unittest discover -s tests -p test_admin_console.py`。

## Docker 开发

从仓库根目录执行：

```powershell
python infra/docker/prepare-env.py
cd infra/docker
docker compose -f compose.yml -f compose.dev.yml --profile full up -d --build --wait
```

访问 http://localhost:3101 ，开发账号 `shenzhi`，密码 `shenzhi-dev`。Session Secret 由现有 prepare-env.py 随机生成到本地 `.env` 的 `ADMIN_DEV_SESSION_SECRET`，重复运行保持不变。默认凭据只由 dev override 注入 Backend，生产 override 清空管理认证配置，并拒绝在非 development 环境使用该密码。

Admin 与 Backend 共享网络命名空间，Vite 以 `127.0.0.1:8000` 代理 Backend，Backend 保留 loopback、Cookie 和写操作门禁。3101 端口仅在宿主 `127.0.0.1` 发布；Vite 仅在显式 Docker development 模式接受容器入口流量，校验本地 Host/Origin、拒绝 cross-site 请求并移除转发 Header。普通 Web 不代理管理 API。

开发 Admin 定义在 compose.dev.yml 的 full profile；生产需显式叠加 compose.admin.yml。开发镜像只安装现有锁定依赖。源码同步可执行 `docker compose -f compose.yml -f compose.dev.yml --profile full watch --no-up admin`。Backend 重建/重新创建后，执行相同 up 命令重新关联 Admin 网络命名空间；不要只更新 Backend 后继续使用旧 Admin 容器。

## 认证与部署边界

认证独立封装于 Backend `core/admin_auth.py`。常量时间比较账号密码；会话包含签发时间、随机 nonce 与 HMAC-SHA256 签名；校验签名、时间及配置。轮换密码或密钥使已有会话失效。退出清除浏览器 Cookie；V1 无服务端撤销列表，被复制的已签发 Cookie 在过期或密钥轮换前仍有效。

Cookie 为 HttpOnly、SameSite=Strict，Path 限制 `/api/v1/admin-console`，HTTPS 请求设置 Secure，不写入 localStorage。不信任管理员身份 Header。登录通过凭据校验，其余路由通过管理会话校验。

生产部署已确定采用 **SSH 密钥＋本地隧道，目标为 Admin 免账号密码**，完整拓扑、命令模板及上线条件见 [部署文档：Admin 管理入口](../../docs/engineering/deployment.md#四admin-管理入口ssh-密钥与隧道)。管理入口只监听服务器 loopback，提供 `dist/` 静态构建并同源代理管理 API；公网入口必须阻断管理路径。两端本机 HTTP 链路之间由 SSH 加密，不对公网提供 HTTP 管理入口，不开放 CORS。

**当前支持 `local_password` 与显式启用的 `ssh_tunnel`，两者均使用管理 Cookie。** 隧道模式校验 loopback、入口 secret、Host/Origin，并保留同源写保护和稳定审计身份。上文环境变量及启动命令描述本地开发方式；真实 SSH 与公共代理仍需部署验收。

## 数据与后续边界

用户查询复用 `admin_users.list_users` 与 `AdminUsersResponse`，多规则 Token 单列显示，不相加；缺失权益为未知，Partial 为已知下界，预留不等同于实际消耗。

兼容 `/capabilities` API 继续读取 Agent `/internal/v2/config`；新 Agent 目录通过 `/internal/v2/management` 读取 Provider、Model、Tool、Skill。连接不继承环境 HTTP 代理，不可用返回503，不伪装为空。目录状态不是授权或健康状态。

正式套餐的 Policy 发布、权益分配、停用/恢复及审计已接入；能力目录本身仍只读，不提供任意能力编辑。请求期间不执行离线 export_capabilities 脚本。原 Web 用户管理页面及菜单入口已移除，管理界面统一使用本工程；旧 Backend `/api/v1/admin/*` API 与 `SHENZHI_ADMIN_USER_IDS` 配置已移除。


## 正式套餐与 Admin 操作

套餐固定为 Basic/basic（200000）、Pro/pro（1000000）、Research/research（3000000）Token/上海自然日，暂时全部免费。计量输入＋输出；仅 Research 包含 deep-research。模型与通用工具/技能不按套餐区分，来自同一受控 Worker 能力导出。新用户默认待分配，旧注册通知端点仅兼容返回 initialized=0，不再自动授予 Free。

先在 Backend 执行迁移（先备份，使用本地服务环境）：

```powershell
uv run --env-file .env alembic upgrade head
```

发布流程：

1. 完成最终 Worker 代码/环境配置，在 Agent 目录执行 `uv run --env-file .env python -m agent_app.export_capabilities --output workspace/formal-capabilities.json`。
2. 在 Backend 目录生成发布包：

```powershell
uv run --env-file .env python -m app.services.agent_entitlements.plans --capabilities ../agent/workspace/formal-capabilities.json --release 20261120 --model-budgets workspace/reviewed-model-budgets.json --risk-profile <APPROVED_PROFILE> --output workspace/formal-plans-20261120.json
```

三个版本为 basic-v1-20261120、pro-v1-20261120、research-v1-20261120。正式套餐不再使用 --call-upper-bound：每日规则的 reservation_units/call_upper_bound 均为0，明确由 dynamic_model_budget=true 的独立逐调用预算路径处理，不代表无限授权。旧策略仍保留旧字段语义。

`--model-budgets` 是独立、部署审批后的逐模型风险约束文件，三个套餐共用；没有默认 Token 证明或虚构的上下文窗口。模板如下（占位符须替换成审核后的整数）：

```json
{
  "model:<REGISTRY_ID>": {
    "schema_version": 1,
    "input_basis": "risk_assessed_utf8_v1",
    "input_overhead_tokens": "<REVIEWED_FRAMING_ALLOWANCE>",
    "context_window_tokens": "<VERIFIED_CONTEXT_WINDOW>",
    "max_output_tokens": "<VERIFIED_OUTPUT_LIMIT>",
    "output_limit_semantics": "completion_including_reasoning"
  }
}
```

输入预算取完整请求正文（不含协商的 max_tokens）的 UTF-8 字节数＋审批的封装余量，仅是 risk_assessed_utf8_v1 风险估算，绝不是 tokenizer 证明。只有负责人确认模型/Provider 的上下文、输出参数和思考 Token 均受该输出限制时才能配置该模型；不支持此语义的 Provider 保持阻断。批准风险策略接受估算及 Provider 超额风险，不承诺数学意义上不超支。

`model_risk_profile=null` 的历史包会拒绝 TOKEN_BOUND_UNPROVEN；生成命令现在提前拒绝风险配置或逐模型预算为空的发布包。指定 `--risk-profile <APPROVED_PROFILE>` 和 `--model-budgets <BUDGET_JSON>`，并在控制台填写对应风险记录。允许仅为本次要启用的模型提供约束；其他模型仍拒绝 MODEL_BUDGET_UNCONFIGURED，不因共享风险引用而放行。`--model-budgets` 按模型ID合并覆盖旧包配置，保留未指定的其他模型预算。

逐模型预算由部署负责人在本地审核文件中维护，不再提供仓库内固定 Provider 预算。使用 `--model-budgets <REVIEWED_MODEL_BUDGETS_JSON>` 合并覆盖，或通过 `--previous-bundle` 复用已经批准的预算。历史 `context_window_tokens` 字段继续兼容；真实上下文上限仅采用 Worker Registry 明确声明的值。

3. Admin → 套餐管理 → 发布与迁移 → 发布套餐新版本 → 上传发布包 → 填写原因、Policy 审批引用、模型风险审批引用（如有）→ 确认发布。Backend 校验受控身份摘要、固定三档规则与当前 Agent 的公开 Model/Skill 集合。Tool build 身份由离线导出和管理员审批保证，当前配置 HTTP 接口无法远程验证 build 摘要。
4. 用户管理 → 勾选一个/多个用户 → 选择套餐、原因 → 预览 → 确认执行。成功、失败和部分成功均分用户返回；失败不覆盖该用户权益。网络失败保留操作 ID 供原请求重试。
5. 历史用户：套餐管理 → 发布与迁移 → 历史账号迁移预览，填写明确的注册时间截止点，预览待分配用户后批量初始化 Basic。只补缺失分配，不覆盖现有特殊/禁用/人工权益；有历史 Free 的用户可在用户列表由管理员显式调整。
6. 停用/恢复使用同一预览、确认和审计流程。审计页查看管理员、时间、操作 ID、原因、审批引用及各用户前后套餐/Policy。

写 API 全部要求独立管理会话及 X-Admin-Request: 1，不开放 CORS，local-only 限制保持。正式套餐 CLI assign/install-policy 不作为分配/发布旁路。

| 方法 | 路径（前缀 /api/v1/admin-console） | 说明 |
|---|---|---|
| GET | /plans | 发布版本、固定额度、能力与风险门禁状态 |
| POST | /plans/publish | 发布三档不可变 Policy；operation_id/reason/approval_ref/policies/capabilities/risk_approval_ref |
| POST | /entitlements/assign | user_ids（最多100）、action（assign/disable/restore）、plan_id、policy_revision、reason、operation_id、preview、initialize_only |
| POST | /migration/preview | before（带时区）、limit（最多100）；只读预览历史缺失用户 |
| GET | /audit?page=1&page_size=20 | 管理操作审计 |

## 预算、切换和回滚

新 Policy 的 reservation_mode=per_call、dynamic_model_budget=true：签名 Grant 初始保留稳定 allocation 身份而不预占 Task 额度；每次 Permit 在 owner→grant 锁内检查共享每日余额，原子增加 call-held 和账本，然后才允许 start。重复请求不会重复预留。已测量用量沿原结算释放确定未用部分；Partial/Unknown/Failed 缺证据继续保留未决额度；只有封闭证明才可释放未启动调用。历史 task_fixed Grant 继续按原逻辑结算。

正式 daily-tokens 使用固定 quota_pool=formal-daily-tokens-v1，同日跨计划/版本共享计数；旧上海自然日 daily-tokens 窗口的余额也纳入同一额度检查，但不合并限额或不同规则。切换时保留 used/held，调整当前额度。降级后余额可为零，不抹去历史使用。

存在未关闭 Grant 时变更 Policy 返回 ACTIVE_GRANTS_REQUIRE_DRAIN。已签权限不自动迁移；已启动调用继续结算。停用立即拒绝新 Permit/start；恢复保留原分配和原余额。新发布不会自动迁移现有用户。自然日跨日、Grant TTL、模型上下文/输出约束仍有效，长任务不会自动跨日续签。单次输出可依据每日剩余额度缩减；本期没有自动延长 Grant TTL。

迁移028只新增 agent_plan_releases 发布指针表；历史 Policy/Grant/Usage/Audit 不更新或删除。回滚先停止新准入并排空已签 per_call Grant，保留 Control、结算与 Usage Worker；不得在存量任务中直接回退预算代码。撤回发布应新建版本并显式重新分配。数据库 downgrade 只移除发布指针表，不恢复旧自动 Free，也不删除历史账本；应用回滚前须保留授权/用量接收能力。

上线前必须核对：迁移028、独立本机管理员密钥、Agent 的 authorized 准入、隔离角色 Token、签名私钥/历史公钥、实际 Worker 导出/版本、真实模型风险批准、Usage Worker 与持久 spool。未完成风险批准时界面可分配套餐，但模型门禁继续拒绝；不得称已具备生产模型授权。Web Deep Research 页面仍是演示工作台，真实 Skill 权限走 Agent 任务链路，普通科研检索不依赖该专用 Skill。


## 动态单次模型预算

ModelCallBudgetRequest 随 CallIntent 和 CallPermitRequest 传递：input_bytes、requested_output_tokens、model_max_output_tokens、model_context_window（未知为 null）、basis。Backend 仍验证相同的风险 profile 和签名能力，在原 owner→grant 锁内计算输入风险预算 I，再批准 O=min(请求输出、Agent 模型输出上限、审批的模型输出上限、模型上下文余量、每日可用-I)，要求 O>0；本次原子预留 I+O。

Permit 的 model_budget 记录 basis/input_tokens/output_tokens/reserved_tokens。Control 把批准结果与 Permit token allocations 核对并通过唯一 start 回执交付 Worker。Provider 最终 max_tokens 必须等于批准 O；Worker 发送前再次检查其值和请求正文摘要。动态摘要定义为 body_without_max_tokens：正文摘要与已批准 O 共同绑定最终请求，任何消息/工具/思考参数改动都拒绝。参数降级、外层重试、摘要会构造新请求并重新取得 Permit，不复用发送权。

预算协商字段是持久 JSON 中的可选扩展，不需新增数据库迁移；缺省字段序列化时不写出，历史 Permit/Intent/Usage 保持原始兼容。签名 Grant 的 model_call_budget=dynamic_v1 区分新路径。历史 Grant 按其原风险审批与固定预算路径执行及结算，不原地更换旧授权；部署时应排空旧任务或保留对应版本 Worker。新协议混部不匹配时拒绝，不降级绕过。Unknown/Partial、封闭证明、超额和账本规则不变。

审计列表的 `target_accounts` 通过记录中的用户 ID 批量关联当前账户邮箱（每项为 `user_id`、`email`）。页面优先显示当前邮箱，账户不存在或邮箱为空时回退到 ID；未记录目标账户的操作显示“—”。这是只读展示补充，不是操作发生时的邮箱快照，原始审计 payload 保持不变。

## Agent Registry 只读目录与生产入口

Provider、Model、Tool、Skill 的列表、详情、参数 Schema 与文档预览见 [目录说明](../../docs/admin/agent-management-console.md)。浏览器不直接调用 Agent，不持有内部 Token；Backend 通过独立 `AGENT_MANAGEMENT_TOKEN` 读取真实 Registry。模型资料及价格为静态快照，没有官网刷新或配置写接口。

生产支持显式启用 SSH 隧道认证与独立 Nginx 静态镜像，开发账号登录继续保留。默认生产 override 仍关闭 Admin；部署时显式叠加 `compose.admin.yml`，通过独立 Session Secret 与入口 secret 隔离公共代理，配置及上线条件见 [Admin Docker 指南](../../infra/docker/ADMIN.md)。现有套餐发布、权益调整与审计继续使用原有预览/确认流程；不新增 Agent 专用操作审计。
