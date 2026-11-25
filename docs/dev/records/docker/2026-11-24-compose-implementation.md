# Docker Compose 实施与验收记录

日期：2026-11-24（Asia/Shanghai）。工作分支：`chore/docker-compose-infra`。
起始工作区干净；fetch 后 HEAD 与 origin/dev 均为 `60188121277bdeb738f19e6e414d82e386533b6c`。
因此在当前 checkout 安全创建任务分支，无需额外 worktree。未 commit、push、建 PR 或操作远程部署。

## 1. 当前工程与检查结论

- 阅读根 README、ONBOARDING、根/Web/Backend AGENTS、架构、部署（含 Admin SSH 约定）、认证迁移说明及服务入口。
- Web 为 Next.js 16.2.12（锁定依赖）、React 19、独立 pnpm lock；已有 standalone 输出。
- Backend 为 Python 3.12、uv、FastAPI `app.main:app`，Alembic 管理业务表，认证表另由 Web SQL 管理。
- Agent API 为 `agent_app.main:app`；执行 Worker 为 `agent_app.worker_main`；Usage Worker 为 `agent_app.usage_worker`。
- Backend 和 Agent 均依赖 editable `packages/agent-contracts`。保留两份 uv.lock 与 Web pnpm-lock 原样。
- Agent Task/Run/Event、Lease、Control、Outbox/用量事实持久化于独立 Agent PostgreSQL；Workspace 与 Usage Spool 是文件持久化。
- 本机已存在 V2 authorized / v1 drain_only / Worker protocol 2 配置、角色凭据与签名文件；已按白名单复制到独立 Docker 配置，无降级。
- 原仓库没有现行 Dockerfile/Compose；旧自动部署链路已撤除，不恢复 Watchtower/GHCR 发布。
- 本机原有 `shenzhi-postgres` 正在运行；历史 `m0-c1-postgres-20261118` 已停止。所有旧容器/卷保留，未连接或迁移旧数据库。
- Admin 是独立 Vite 应用，现有认证要求 Backend 看到 loopback 来源，SSH 免密码模式尚未实现。
  本次不提供 Admin 容器，不放宽来源校验；保留原生入口与现有认证。

## 2. 编排设计

| 服务 | 职责与依赖 | 默认宿主端口 |
|---|---|---|
| postgres | PostgreSQL 16；空卷初始化业务库和 Agent 库 | 127.0.0.1:55432；prod 无映射 |
| auth-migrate | 依序应用三个现有认证 SQL，记录名称/校验和 | 无 |
| backend-migrate | auth 完成后执行 Backend Alembic | 无 |
| backend | 迁移完成后启动单实例 FastAPI | dev 127.0.0.1:8800 |
| web | 等 Backend ready；生产使用 standalone | 127.0.0.1:3300 |
| agent-migrate | 独立库 Alembic | 无 |
| agent-api | 等 Agent 迁移；内部 Task/Run/事件与配置 API | dev 127.0.0.1:8811 |
| agent-worker | 等 Agent API ready；执行与 Lease 协议沿用原实现 | 无 |
| agent-usage-worker | V2 Outbox 投递/恢复/对账 | 无 |

默认 Compose 网络提供服务名解析；不将网络设为 internal-only，保证科研/模型外部 API 的出站访问。
内部地址为 `postgres:5432`、`backend:8000`、`agent-api:8101`；浏览器 origin 单独配置。
迁移入口通过 PostgreSQL advisory lock 串行化，启动进程不各自抢跑迁移；Backend 和 Agent 分库。
API healthcheck 检查 HTTP 存活、数据库连通和迁移版本存在；Web healthcheck 穿过 BFF 到 Backend。
Worker 只报告进程运行状态，没有虚构业务 healthcheck；轮询日志和实际任务必须另行核验。
Named volumes：postgres-data、agent-workspace、agent-spool；开发另有可重建 web-next 缓存卷。
API 与两个 Worker 使用同一 UID 10001、Workspace 与 Spool；日志轮转 10MB ×3。

Profile：默认 infra-only；`app` 为 Web/Backend；`agent` 为 API/执行 Worker；`usage` 为用量恢复；`full` 全部。
V2 联调必须 full 或显式组合 usage，不可省略用量恢复服务。
生产 override 禁用调试旁路并固定 authorized/drain_only/protocol=2；未配置密钥/批准策略时拒绝模型授权。

## 3. 文件变更与保留项

新增：

- 根 `.dockerignore`、`.gitattributes`。
- `apps/web/Dockerfile`、`apps/backend/Dockerfile`、`apps/agent/Dockerfile`。
- `infra/docker/compose.yml`、`compose.dev.yml`、`compose.prod.yml`。
- `infra/docker/.env.example`、`env/web.env.example`、`env/backend.env.example`、`env/agent.env.example`。
- `infra/docker/prepare-env.py`、`postgres/init-databases.sh`。
- `infra/docker/scripts/migrate.py`、`healthcheck.py`、`smoke.py`。
- `infra/docker/README.md`、本记录。
- `apps/web/tests/backend/admin-entrypoint.test.ts`。

修改：根 `.gitignore`、README、ONBOARDING、`docs/engineering/deployment.md`、
`apps/web/clients/backend/forward.ts`（公共 BFF 在转发前拒绝 Admin 路径，包括编码分隔符/路径段）。

保留：原生启动命令、应用 `.env.example`、真实原生环境文件、依赖/锁文件、数据库迁移 SQL/Alembic、Agent 业务协议。
生成的 Docker `.env`、`env/*.env`、私钥/公钥副本只在忽略目录中；无缓存、数据库文件或真实环境文件进入变更集。

## 4. 环境变量管理

`prepare-env.py --from-local` 只读原生 Web/Backend/Agent 配置，按模板白名单复制必要值；
不复制 VERCEL_OIDC_TOKEN、Admin 密码或服务器配置。Docker 配置与宿主原生配置相互独立。
缺失内部凭据使用随机值，已有有效 Docker 值保留且两端不一致时报错；首次转换地址，后续不回写宿主文件。
首次关闭 BACKGROUND_JOBS_ENABLED，避免联调环境自动启动原生定时任务。
V2 签名私钥和公钥清单分别存放、只读挂载，Agent 不获得私钥目录。已验证复制后的 kid、公钥和私钥能完成签验。

主要变量名（完整字段见三个 Docker env 示例）：

| 范围 | 变量 |
|---|---|
| Compose | COMPOSE_PROJECT_NAME、POSTGRES_USER、POSTGRES_PASSWORD、POSTGRES_DB、AGENT_DB、POSTGRES_PORT、WEB_PORT、BACKEND_PORT、AGENT_PORT、IMAGE_PREFIX、IMAGE_TAG |
| Web/Backend | BUSINESS_BACKEND_URL、BACKEND_BFF_SECRET、BACKEND_ALLOW_INSECURE_LOCAL_BFF、DATABASE_URL、CHAT_DATABASE_URL、KNOWLEDGE_BASE_API_URL、KNOWLEDGE_BASE_TIMEOUT_SEC |
| Web 认证 | BETTER_AUTH_SECRET、BETTER_AUTH_URL、BETTER_AUTH_TRUSTED_ORIGINS、EMAIL_PROVIDER、ALIBABA_CLOUD_ACCESS_KEY_ID、ALIBABA_CLOUD_ACCESS_KEY_SECRET、ALIYUN_DIRECTMAIL_REGION_ID、ALIYUN_DIRECTMAIL_ENDPOINT、AUTH_EMAIL_FROM、AUTH_EMAIL_FROM_ALIAS、GITHUB_CLIENT_ID、GITHUB_CLIENT_SECRET |
| 人机验证 | TURNSTILE_ENABLED、TURNSTILE_SECRET_KEY、TURNSTILE_EXPECTED_ACTION、TURNSTILE_ALLOWED_HOSTNAMES |
| Next 公开构建变量 | NEXT_PUBLIC_KNOWLEDGE_SOURCE、NEXT_PUBLIC_PAPER_THUMBNAIL_ENABLED、NEXT_PUBLIC_TURNSTILE_SITE_KEY |
| Backend | ENVIRONMENT、BACKGROUND_JOBS_ENABLED、PAPER_RESOURCE_TIMEOUT、PAPER_MAX_SIZE_MB、OPENREVIEW_USERNAME、OPENREVIEW_PASSWORD、CONFERENCE_GITHUB_TOKEN、STATS_SERVICE_TOKEN、CRON_SECRET |
| Agent 网络/文件 | AGENT_DATABASE_URL、AGENT_INTERNAL_URL、BACKEND_INTERNAL_URL、BACKEND_ENTITLEMENTS_URL、AGENT_WORKSPACE_ROOT、AGENT_USAGE_SPOOL_ROOT、AGENT_DEMO_MODE |
| 准入/认证 | AGENT_V2_ADMISSION、AGENT_V1_ADMISSION、AGENT_WORKER_PROTOCOL、AGENT_SERVICE_TOKEN、AGENT_GATEWAY_TOKEN、AGENT_FACT_READER_TOKEN、AGENT_CONTROL_TOKEN、AGENT_WORKER_TOKEN、AGENT_AUDIENCE、AGENT_GRANT_ISSUER、AGENT_GRANT_SIGNING_KID、AGENT_GRANT_PRIVATE_KEY_FILE、AGENT_GRANT_PUBLIC_KEYS_FILE、AGENT_ALLOW_TEST_POLICY、AGENT_OBSERVATION_ADMISSION_REVISION |
| 能力/用量 | AGENT_MODEL_ROUTE_REVISION、AGENT_TOOL_CONFIGURATION_RELEASE、AGENT_USAGE_OUTBOX_CAPACITY、AGENT_USAGE_BATCH_SIZE、AGENT_USAGE_MAX_ATTEMPTS、AGENT_USAGE_RETRY_BASE_SECONDS、AGENT_USAGE_RETRY_MAX_SECONDS、AGENT_USAGE_POLL_SECONDS |
| Provider | DASHSCOPE_API_KEY、DEEPSEEK_API_KEY、ZHIPU_API_KEY、AUTODL_API_KEY、AUTODL_MODELS、AI_ALLOWED_MODELS、AI_DEFAULT_MODEL、AI_AGENT_DEFAULT_MODEL、AI_MODEL_REGISTRY_FILE、AI_TIMEOUT_SEC、TAVILY_API_KEY、SEARXNG_BASE_URL、EXA_API_KEY、SKILLS_VENDOR、AGENT_DISABLE_THINKING；按需导入非空 Provider BASE_URL/MODEL 覆盖项 |

Compose 插值文件与容器 env_file 分离；app env 使用 raw 格式，避免 `$` 被二次展开。
Next 公开变量同时用于镜像构建，修改后必须重建生产 Web；服务端凭据不作为 build args，不进入 NEXT_PUBLIC。
镜像中已检查无原生 `.env` / `.env.local`，Python 本地包可导入。

## 5. 经过验证的操作

PowerShell（仓库根目录）：

```powershell
python infra/docker/prepare-env.py --from-local
cd infra/docker
docker compose up -d --wait postgres
$dc = @('-f', 'compose.yml', '-f', 'compose.dev.yml', '--profile', 'full')
docker compose @dc up -d --build --wait
docker compose @dc exec -T backend python /opt/docker/smoke.py --full
docker compose @dc ps -a
docker compose @dc logs --tail 100 backend
docker compose @dc restart backend
docker compose @dc down
```

Linux 使用 `python3`，把 `docker compose @dc` 换成
`docker compose -f compose.yml -f compose.dev.yml --profile full`；容器/迁移运行命令相同。
Linux 实机及密钥 UID/文件权限适配未验证，按运行指南配置。生产是在 Windows Desktop 的 Linux Engine 验证。
正常停止不用 `-v`。全栈停止后可按同样命令恢复数据。本次最终保留完整 dev 栈运行，便于本机审查。

## 6. 实际验收状态

| 状态 | 项目和证据 |
|---|---|
| 已验证通过 | base/dev/prod Compose config --quiet；真实 Docker Desktop Linux Engine 构建全部镜像 |
| 已验证通过 | PostgreSQL 双库、认证 3 个 SQL、Backend 028_formal_plans、Agent 0003_agent_metering；迁移重复执行成功 |
| 已验证通过 | Web/Backend/API ready、BFF→Backend→Agent 配置请求、Worker V2 claim 连续 200、Usage Worker 运行且能加载 V2 控制配置 |
| 已验证通过 | 缺失 BFF/Agent 凭据拒绝、V2 旧 service token 不可替代 gateway token；Backend Admin 非 loopback 拒绝，Web Admin 404 |
| 已验证通过 | Better Auth get-session 端点、认证表存在；不等于注册/邮件登录成功 |
| 已验证通过 | 经 Web BFF 的论文检索 HTTP 200、业务 code=0；未声称检索结果质量/全部上游能力已验收 |
| 已验证通过 | Workspace/Spool 跨进程读写；全部 force-recreate 及 down/up 后标记仍在；业务库持久标记保留 |
| 已验证通过 | Web 源码修改无需重启生效；Backend 源码变化触发 reload；单服务重启恢复；Infra Only 独立启停 |
| 已验证通过 | 无源码挂载的 standalone 生产配置启动与 Smoke Test；生产实际仅映射 Web loopback 端口 |
| 已验证通过 | tsconfig.test 编译、相关 ESLint、13/13 BFF 回归测试、Python compileall、git diff --check、env 初始化幂等 |
| 已实现但未验证 | Linux 宿主实机、真实 HTTPS 代理接入、备份恢复演练、生产镜像仓库发布、CI/CD、带未决模型调用的重启恢复 |
| 依赖授权/业务初始化暂未验证 | 新隔离库没有用户套餐/Policy 分配；不自动导入旧库或授予权益，真实 Task/Run/Event/Lease/Outbox 的业务执行恢复未验收 |
| 依赖外部配置暂未验证 | 真实模型任务、邮件投递、OAuth/Turnstile 注册登录、完整用户会话业务持久化 |
| 验证失败（已修复） | Windows bind mount 新路由未被 Turbopack 识别；容器开发改用 Webpack polling，修改前后响应实测通过 |
| 验证受环境限制（已复验） | BFF 测试首次被沙箱 loopback EACCES 拦截；在允许本机 loopback 的执行环境复跑，同组 13 项全部通过 |

持久化探针仅在本任务隔离库新增 `docker_runtime_probe` 单行表，Workspace/Spool 中保留 `.docker-smoke-persistence` 标记；
没有新增真实模型 Task，不清空或删除任何用户数据。进程存活、健康检查、内部通信与真实业务验收按表分别记录。

## 7. 风险与后续工作

当前如需完成真实 AI 产品验收，必须在新库按现有受控流程初始化用户、批准/发布 Policy、模型风险预算并分配权益；
本次不自动复制原生账号/套餐或伪造审批。签名、角色、网络配置已验证，不表示新库已有生产授权。
Admin 容器化及 SSH 免密码仍受 deployment.md 的明确前置条件约束，不在本次放宽。
镜像升级后必须显式重跑迁移；导入无认证迁移账本的既有数据库需先制定 baseline，不能跳过已有表错误。
生产上线还需备份与恢复、域名/TLS、外部依赖与回调、Worker build/digest 与正式模型预算批准、监控和容量检查。
Lease/fencing 可防过期 Worker 覆写，不能据此承诺外部模型调用恰好一次；运行中升级要排空并保留恢复路径。

## 8. Git 与数据安全

HEAD 未变，分支为 `chore/docker-compose-infra`，全部修改未暂存、未提交。
原生配置未修改；真实 Docker env 和签名副本已由 git check-ignore 核对。
旧 `shenzhi-postgres` 持续运行，历史容器和旧卷均保留。
本次新增卷仅带 `shenzhi-docker_` 前缀；从未执行 `down -v`、volume rm、prune、reset --hard 或 clean。
交付统计（含未跟踪新增文件）：25 个文件，新增 1160 行、删除 0 行；真实配置与缓存不计入变更集。
