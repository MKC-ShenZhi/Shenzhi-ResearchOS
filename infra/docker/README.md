# Docker 运行体系

应用目录维护镜像；这里维护运行编排。原生 Node/Python 启动方式继续有效。
app/full 还包含内部 Payment 容器，默认不要求商户凭据、不发布宿主端口。
`prepare-env.py` 生成 `env/payment.env` 并与 Backend 配对独立服务凭据；支付模式、密钥挂载及 Mock 验收见 [Billing](../../docs/billing/README.md)。
所有命令从本目录执行，要求 Python 3.12+、Docker Engine/Desktop（Linux containers）、Compose >=2.32.2（开发使用 Watch initial_sync）。
首次拉镜像、安装锁定依赖需要访问 Docker Hub、GHCR、npm 和锁文件指定的 PyPI 镜像。
Windows 使用 Docker Desktop WSL2 后端，确认 `docker version` 的 Server 可用。
Linux 安装 Docker Engine 和 Compose plugin；不要使用旧 `docker-compose` v1。

## 首次配置

PowerShell（仓库根目录）：

```powershell
python infra/docker/prepare-env.py --from-local
cd infra/docker
docker compose --profile full config --quiet
```

Linux 同样运行 `python3 infra/docker/prepare-env.py --from-local`，随后 `cd infra/docker`。
没有本地配置的同学去掉 `--from-local`，再填写外部模型、知识底座及邮件配置。
脚本只导入 Docker 示例声明的变量（含注释列出的非空 Provider 地址覆盖项），不复制编辑器 OIDC 凭据和 Admin 密码；随机生成仅供 dev override 使用的 ADMIN_DEV_SESSION_SECRET，重复运行保留。
原文件保留；已存在的有效 Docker 配置不被覆盖，缺失或空的必需凭据会补齐，跨服务凭据不一致时报错。
生成的 `.env` 和 `env/*.env` 沿用对应 `.env.example` 的中文分组与配置说明；再次执行会按最新模板更新注释。
模板未声明的已有配置项保留在文件末尾；自写备注请同步维护在模板中，脚本不会保留本地文件中的自定义注释。
可导入字段为空时会补入非空的本机值；共享凭据及 audience/issuer 优先复用已有非空 Docker 值，冲突时拒绝写入。
空 Provider BASE_URL 没有本机覆盖值时保持未设置，以使用 Registry 默认值。
首次为缺失的内部凭据生成随机值，为容器改写 DSN、服务地址和工作目录；再次执行不会轮换已有凭据。
签名密钥不会自动生成或轮换：路径为空时优先复用已复制文件，其次导入本机文件；V2 启用时缺少签名文件会失败。
已有非空签名路径必须指向可读、非空的普通文件；`/run/secrets/<服务>/...` 按本地 `secrets/<服务>/` 校验，
其他绝对路径按本机文件校验、相对路径从 `infra/docker` 解析。自定义容器挂载路径须有可验证的本机对应路径。
全部校验完成后才暂存并替换输出文件；写入失败会尝试恢复已替换文件，重复运行不重写内容不变的文件。
已有端口占用时修改 `.env`；修改 `WEB_PORT` 后须同时更新 `env/web.env` 中的浏览器 origin。
脚本限制生成 DSN 的数据库用户名、密码、库名使用字母、数字、`_` 和 `-`。
首次使用随机密码；更改已初始化 PostgreSQL 的环境变量不会自动修改数据库角色密码。

真实 `.env`、`env/*.env` 和 `secrets/` 已忽略；不要提交、粘贴 `docker compose config` 的完整输出。
用 `config --quiet` 检查。不要把密钥放进命令行、Docker build args 或 `NEXT_PUBLIC_*`。
Linux V2 导入后，需让 UID 10001 能读取对应签名文件：由文件所有者/管理员将
`secrets/backend` 和 `secrets/agent` 的所有者设为 `10001:10001`，目录权限 700、文件 600。
这一步不应放宽到所有用户可读。Windows Desktop 由文件共享权限控制。
Agent 仅挂载公钥目录，Backend 仅挂载私钥目录；两个目录不互相共享。
自定义 `AI_MODEL_REGISTRY_FILE` 等本机文件路径时需另加只读挂载及容器路径；脚本不会猜测这些文件的部署含义。
外部服务若在宿主机 loopback，容器内应改用 `host.docker.internal`（Linux 按需添加 host-gateway），
并确保宿主服务允许该受控连接；外部科研地址只写入真实环境文件。

环境变量分三类：

| 类别 | 文件 | 生效时机 |
|---|---|---|
| Compose 插值：项目名、端口、数据库初始化、镜像标签 | `.env` | Compose 解析时；不会自动注入所有应用 |
| 应用配置和服务凭据 | `env/web.env`、`backend.env`、`agent.env` | 容器创建时；修改后 `up -d --force-recreate <服务>` |
| Next.js 客户端公开配置 | `.env` 中三个 `NEXT_PUBLIC_*` build args | 生产构建时内联；修改需重建 Web |

开发 Web 的公开变量取 `web.env`；生产取构建参数。初始化脚本首次对齐二者，后续请同步维护。
Docker env_file 使用 raw 格式，值不加外层引号，`$` 和 `#` 保留为值。
脚本导入支持常规单行 dotenv；复杂多行配置请人工配置，不做 Shell 求值。

模型 Key 配置在 `env/agent.env`，内置型号与能力由 Catalog 维护，无需填写型号变量。
OpenLux 固定白名单、真实探测状态和默认优先级见 [模型配置指南](../../docs/engineering/llm-api-foundation.md)。
三个 Agent 服务使用同一份 env_file；修改环境后按下列命令重新创建容器：

```powershell
docker compose -f compose.yml -f compose.dev.yml --profile full up -d --no-deps --force-recreate agent-api agent-worker agent-usage-worker
```

`restart` 不重新加载 env；生产使用对应的 prod 文件组合并先排空任务。具体能力声明及套餐授权要求见
[OpenLux 接入说明](../../docs/engineering/llm-api-foundation.md#openlux-验证入口)。

## 四种运行模式

### A：只启动基础设施

```powershell
docker compose up -d --wait postgres
docker compose stop postgres
```

默认仅 PostgreSQL，宿主机连接 `127.0.0.1:55432`（端口可配置）。
原生 Web/Backend 指向 `.env` 的 `POSTGRES_DB`，Agent 指向 `AGENT_DB`。
密码取本地 Docker `.env`，不要把容器内 `postgres` 主机名写回原生应用配置。
原生应用仍按 ONBOARDING 运行迁移和启动。

### B：容器开发

```powershell
docker compose -f compose.yml -f compose.dev.yml --profile app up -d --build --wait
# 完整 Agent V2 联调：包含 Usage Worker
docker compose -f compose.yml -f compose.dev.yml --profile full up -d --build --wait
# 在当前终端持续运行 Web 源码同步（上面 app / full 启动方式均适用）
docker compose -f compose.yml -f compose.dev.yml --profile full watch --no-up web
```

开发地址：Web `http://localhost:3300`，Backend `http://localhost:8800`，Agent API `http://localhost:8811`；full profile 另启 Admin `http://localhost:3101`，开发账号 `shenzhi` / `shenzhi-dev`。
Admin 与 Backend 共享网络命名空间，代理走 `127.0.0.1:8000`，保持 Backend local-only；Vite 显式开发入口校验 Host/Origin，忽略转发身份。3101 仅绑定宿主 loopback，Session Secret 由 prepare-env.py 随机生成。
Admin 源码同步使用相同 watch 命令末尾的 `admin`（或 `web admin`）；Backend 重建/重建容器后用同一 full up 命令重新关联 Admin 网络命名空间。
所有映射均绑定宿主 loopback；内部调用使用 `backend:8000`、`agent-api:8101`、`postgres:5432`。
Web 使用 Turbopack + Compose Watch，将源码同步到容器内部，不挂载宿主源码、env 或 node_modules；.next 使用独立 named volume。
Python 环境位于 `/opt/venv`，源码挂载不覆盖环境；本地 contracts 包以相同仓库相对路径 editable 安装。
源码变化触发 Turbopack Fast Refresh；Next/TypeScript/PostCSS 配置和 proxy 变化使用 `sync+restart`；
package.json、pnpm-lock.yaml、pnpm-workspace.yaml 变化使用 `rebuild`。
Watch 需保持运行；Ctrl+C 仅停止同步。单独 `up -d` 不会后台开启 Watch。
Watch 停止期间发生删除/重命名后，先 `up -d --build --force-recreate --no-deps web` 重建 Web，再启动 Watch，避免残留文件。
Backend Uvicorn reload；Agent 三进程按既有运行约定手动一起重启：

```powershell
docker compose -f compose.yml -f compose.dev.yml --profile full restart agent-api agent-worker agent-usage-worker
```

Worker 运行中强制重启可能中断模型调用；正式任务应先停止新准入、排空并保留结算恢复服务。
Lease/fencing 和 Outbox 按现有数据库协议恢复，不承诺被中断的外部模型请求恰好执行一次。
依赖锁文件变化后重建镜像；Web .next named volume 仅是缓存，不能删除数据库卷来解决构建缓存问题。
如果出现 `Module not found`（例如新增订阅页面提示缺少 `qrcode`），先确认已重建 Web：
`docker compose -f compose.yml -f compose.dev.yml up -d --build --no-deps web`。
普通 `up` 或 `restart` 复用旧镜像，不会安装新增依赖；Watch 启动前已经发生的依赖变化也需要先重建。
Windows NTFS bind mount 较慢时，优先把仓库放入 WSL2 Linux 文件系统后从 WSL 运行，
或选择 A 模式，保留宿主机 Next.js/Python 开发。

### C：完整联调（构建版本，无源码挂载）

```powershell
docker compose --profile full up -d --build --wait
docker compose exec backend python /opt/docker/smoke.py --full
```

默认 `app` 为 Web、Backend、认证/业务迁移；`agent` 为 Agent API、迁移、执行 Worker；
`usage` 为 Usage Worker 及其 Agent API 依赖；`full` 包含全部。
最小 UI/API 开发用 `app`，模型对话需要 Agent；V2 必须同时启用 Usage Worker，不能只启 `agent`。
`agent` 单独启用用于宿主 Backend 混合调试时，需将 `BACKEND_INTERNAL_URL` 和
`BACKEND_ENTITLEMENTS_URL` 配成宿主可达地址。V1 无 V2 存量用量时可以不启 Usage Worker。
全新模板默认 V1 drain_only、Worker protocol=2、Backend V2 disabled；新 Worker 使用独立 Worker Token。
导入本机 V2 时保留 authorized/drain_only/protocol=2 和签名身份，不降级授权、不自动安装 Policy 或授予用户权益。
仅处理历史 V1 Task 的 drain Worker 显式使用 protocol=1 与旧 Service Token。模型授权验收还需按 Admin/entitlements 文档完成批准和分配。
容器新数据库没有原生数据库的用户、Policy 和历史任务；启动成功不代表这些数据已迁移。

### D：生产配置基础（本次不部署）

在独立部署目录准备审核后的生产环境和密钥，设置唯一版本 `IMAGE_TAG`、镜像仓库 `IMAGE_PREFIX`。
在构建机使用与生产相同的 Compose 插值文件构建和发布镜像；部署机运行：

```sh
docker compose -f compose.yml -f compose.prod.yml --profile full config --quiet
docker compose -f compose.yml -f compose.prod.yml --profile full pull
docker compose -f compose.yml -f compose.prod.yml --profile full up -d --no-build --wait
```

生产不叠加 dev 文件。无源码挂载/热重载，数据库无宿主端口，Agent/Backend 无公开端口，
仅 Web loopback 端口供宿主 HTTPS 代理接入。生产迁移服务随启动执行；升级前先备份、停止新准入并排空任务，
不可对运行中的旧版本多实例随意执行不兼容 schema 变更。镜像回滚不代表数据库自动降级。
生产 override 强制关闭本地 BFF 免密、测试 Policy 和 demo，并固定 authorized / drain_only / protocol=2；正式 V2 必须审核
v1 drain_only、protocol=2、隔离角色 Token、签名历史公钥、Worker digest、模型预算、套餐权益及恢复流程。
签名 key、角色配置和授权策略错误时应拒绝调用，不能为启动方便打开旁路。

Admin 仅在开发 override 中定义，基础和生产 Compose 不包含 Admin 服务或 3101 端口。生产 override 清空管理账号、密码及 Session Secret 并禁用管理认证，开发密码在非 development 环境也被拒绝。
生产 SSH 隧道免密码模式和可信专用入口仍待实现，见 deployment.md。不得叠加 dev 与 prod 文件或关闭 local-only 绕过。
公网反向代理必须阻断 `/api/v1/admin-console` 及子路径，不提供 Admin 静态站点。
上线还需域名/TLS、邮件和 OAuth 回调、备份恢复演练、监控告警、容量评估和 CI 镜像扫描/发布。
后台调度器由 `BACKGROUND_JOBS_ENABLED` 控制，默认关闭；只在单个 Backend 实例按部署需要启用。

## 初始化与升级

PostgreSQL 16 使用 named volume；官方 entrypoint 只在空卷创建业务库和 Agent 库。
`init-databases.sh` 不负责表迁移。已有卷修改库名不会自动新建库；请备份并由管理员显式创建。
启动顺序：Postgres ready → auth SQL migration → Backend Alembic → Backend ready → Web；
Agent migration → Agent API ready → 两种 Worker。Backend 不硬依赖 Agent，避免循环依赖。
全部迁移入口使用数据库 advisory lock；认证 SQL 使用名称和 checksum 记录且逐文件事务执行；
Backend 与 Agent 继续使用各自 Alembic。镜像升级后显式重跑迁移：

```powershell
docker compose run --rm auth-migrate
docker compose run --rm backend-migrate
docker compose run --rm agent-migrate
```

认证迁移针对新建库。导入已经应用 SQL 但没有 `docker_auth_migrations` 账本的原生库时会安全失败；
须先备份、核对完整 schema 和既有迁移，由负责人制定 baseline，不能简单忽略表已存在错误。
不要让其他原生 Alembic 命令与容器迁移同时运行：原生命令不参与此 advisory lock。
API healthcheck 增加 DB 连接与 alembic_version 检查，Web healthcheck 穿过 BFF 到 Backend；
这些不代表模型、搜索、任务恢复或登录邮件已通过验收。Worker 没有现成业务健康接口，
不以简单 PID 检查伪装业务就绪；须结合日志、任务 Lease、Outbox 积压和真实任务验收。

Smoke Test 按当前认证 SQL 文件名及与迁移入口相同的 SHA-256 规则核对账本，
缺失记录、额外记录或 checksum 不一致均明确失败，不固定迁移数量。运行维护测试：
`python -m unittest discover -s infra/docker/tests -v`；测试只使用临时目录、合成 SQL 与虚构凭据。

## 常用操作

下面开发操作均使用同一文件组合，避免意外用生产镜像重建开发容器。
PowerShell 可先定义参数数组（Linux 可直接使用完整命令）：

```powershell
$dc = @('-f', 'compose.yml', '-f', 'compose.dev.yml', '--profile', 'full')
docker compose @dc ps -a
docker compose @dc logs --tail 100 -f backend
docker compose @dc exec backend sh
docker compose @dc exec web sh
docker compose @dc up -d web          # 包含必要依赖
docker compose @dc up -d backend
docker compose @dc up -d agent-api agent-worker agent-usage-worker
docker compose @dc restart backend
docker compose @dc build backend
docker compose @dc up -d --no-deps backend
docker compose @dc up -d --force-recreate   # 保留卷
docker compose @dc stop
docker compose @dc start --wait
docker compose @dc down              # 保留持久卷
```

Linux 对应：`docker compose -f compose.yml -f compose.dev.yml --profile full <操作>`。
终止 `logs -f` 用 Ctrl+C，不停止服务。清理本项目已停止容器和网络用 `down`，
`run --rm` 自动清理一次性容器；无需全局 prune。
**`docker compose down -v` 会删除数据库、Workspace 和 Spool 数据，绝不是正常停止命令。**
不在自动验收中执行删卷或全局清理。修改 `COMPOSE_PROJECT_NAME` 会指向另一组卷，看起来像新数据库；
保留原项目名才能恢复原数据。

## 故障排查与备份

- Engine permission denied：确认 Desktop 已启动、Linux containers、当前用户有引擎访问权限。
- 端口冲突：调整 Docker `.env` 和浏览器 origin，不停止未知的本机服务。
- BFF 401/503：两端 `BACKEND_BFF_SECRET` 相同且非空；不能使用 loopback 免密连接跨容器。
- Agent 403/503：检查 V1/V2、角色 Token 隔离、key 挂载权限、audience/issuer、Policy/风险批准；不要通过降级准入解决。
- Worker 活着但无业务：检查日志和真实任务；`app` 模式本就没有 Agent。外部模型/检索失败单独定位。
- init SQL 失败：看 postgres 日志；初始化仅对空卷触发，保留数据并修复，不删卷重试。
- uv/npm 拉取失败：检查 Docker 网络、代理及锁定源可达性；不要改业务依赖版本规避。
- Web dev 源码变化未生效：检查选定 bind mount；Agent 需手动重启；依赖变化重建镜像。

备份应覆盖业务库（含认证）、Agent 库、Workspace、Spool 和受控密钥；任务运行中不能仅拷贝单个卷宣称一致备份。
先停止准入并排空/记录未决执行，按现有结算约定保留 Usage 恢复能力，再做一致性备份。
可用 `docker compose exec -T postgres pg_dump -U shenzhi -d shenzhi -Fc` 作为数据库备份入口；
PowerShell 的旧版本不能安全重定向二进制流，建议在容器内 `pg_dump -f /tmp/backup.dump` 后 `docker compose cp`，
另一个 Agent 库同样备份。备份含个人数据，放在受控仓库外目录并验证恢复。

编排语义参考 [Compose 启动依赖](https://docs.docker.com/compose/how-tos/startup-order/)、
[uv Docker 集成](https://docs.astral.sh/uv/guides/integration/docker/) 与
[Next.js 部署](https://nextjs.org/docs/app/getting-started/deploying)。实际运行结果另记于 `docs/dev/records/docker/`。
