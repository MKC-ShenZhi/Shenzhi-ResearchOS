# Admin 正式部署与验收

## 部署前提

Admin 使用单管理员 SSH 公钥和本地转发。服务器管理端口只发布到 loopback，公开反向代理拒绝 `/api/v1/admin-console` 及全部子路径。Backend 每次校验专用入口密钥、Host、Origin 和管理 Cookie。`local_password` 继续服务受限本地开发。

先完成数据库迁移、角色凭据配置和独立审批公钥部署。API 进程启用 `AGENT_MANAGEMENT_INSPECTOR_ENABLED=true`。Worker 只持有自身上报凭据，Usage Worker 保持独立权限。Backend 无需 Docker Socket。

## 密钥和身份

- 在部署系统生成 32 字节随机入口密钥，保存为 64 位小写十六进制文件，限制为部署管理员和容器所需身份可读。设置 `ADMIN_ENTRY_SECRET_PATH` 为其绝对路径。文件不提交仓库。
- `ADMIN_TUNNEL_PRINCIPAL` 指定稳定审计身份，允许 ASCII 字母数字及 `_.@-`。此身份由可信部署配置绑定，HTTP 不推测 SSH 用户名。
- `ADMIN_SESSION_SECRET` 独立配置，不能复用入口密钥。入口密钥变化会使旧 Cookie 失效。
- 独立审批私钥留在审批者设备。Agent 通过只读公钥文件和 `AGENT_CONFIG_APPROVER_PUBLIC_KEYS` 校验离线证明，保持身份分离开关开启。

## 构建和运行

先按 Docker README 准备应用环境文件，再设置本机部署变量。

```powershell
# 在 infra/docker 下执行，先配置独立入口密钥路径和稳定审计身份。
docker compose -f compose.yml -f compose.admin.yml --profile admin build admin
docker compose -f compose.yml -f compose.admin.yml --profile admin up -d --wait admin
```

`apps/admin/Dockerfile` 的 production target 构建静态产物并由非 root Nginx 服务。容器采用只读根文件系统、临时目录、移除 capabilities 和禁止提权。Admin 与 Backend 共享网络命名空间，Backend 发布的 `127.0.0.1:3101` 是唯一管理入口映射。`/health` 用于容器健康检查。

专用代理会覆盖传入的入口身份 Header，并删除转发来源 Header。Backend 的 `ssh_tunnel` 模式要求该密钥及新鲜管理会话。SSH 隧道内首次 `/auth/me` 校验可信入口并签发 HttpOnly / SameSite=Strict Cookie，管理员无需输入应用密码。退出 Cookie 会话后可重新建立，关闭 SSH 隧道结束远程访问。

公开 Nginx 的每个 server block 应包含 `nginx/public-admin-deny.conf`。现有 Web BFF 的管理路径阻断继续保留。真实服务器外部入口、负载均衡和防火墙须现场验证。

## SSH 账号约束

使用普通专用账号和口令保护的私钥，配置公钥认证，关闭 PasswordAuthentication 和 KbdInteractiveAuthentication。限制 `PermitOpen 127.0.0.1:3101`、允许所需本地转发，关闭 Agent / X11 forwarding、TTY 和非必要会话。生产账号使用普通用户，独立测试 SSH 镜像仅用于隔离验收。

```text
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -i <SSH_PRIVATE_KEY_PATH> -L 127.0.0.1:3101:127.0.0.1:3101 <SSH_USER>@<SSH_HOST>
```

首次连接核对服务器 Host Key。保留现有运维连接，验证新入口后再切换。会话撤销涉及移除对应公钥、终止现有隧道和按需轮换入口或会话密钥。

## Provider Secret 注入与轮换

配置 Spec 仅保存 `AGENT_PROVIDER_SECRET_*` 引用。Worker 环境同时配置 `AGENT_CONFIG_SECRET_REFS` 和 `AGENT_CONFIG_PROVIDER_ORIGINS` 允许列表。真实 Key 由部署平台 Secret 注入环境变量，不进入 JSON、浏览器、发布证明或审计。

推荐流程如下。

1. 在非生产环境准备独立新运行 Key 和独立探测 Key。保留旧 Worker 的旧引用和凭据。
2. 注入新的 Secret Reference，创建候选并记录轮换原因。核对依赖影响和版本差异。
3. 专用探测 Key 验证网络和协议。使用新运行 Key 的候选 Worker 完成实际授权调用，确认鉴权、用量、失败和恢复证据。
4. 独立审批者签名验证摘要，管理员提交证明并发布。核对目标 Worker 的有效版本和真实调用。
5. 排空依赖旧版本的存量任务，确认 Outbox 和结算状态后撤销旧 Key。上游要求立即撤销时，按现有故障处理保留未知用量。
6. 保存配置操作 ID、轮换原因、签名证明、Worker 及调用引用作为轮换审计。原地更换同名引用的值不能仅凭配置摘要证明轮换成功，需同样保留实际调用证据。

`AGENT_HEALTHCHECK_PROVIDER_KEYS` 只注入 Agent API 的探测角色，在线探测拒绝与运行 Key 相同的凭据。配置中更新引用后仍需实际部署和验证，页面不宣布运行 Key 自动轮换成功。

## 回滚和故障处置

发布结果不明时保留原操作 ID，查询回执或对同一发布执行 reconcile。保留旧 Worker、旧制品及仍需使用的旧凭据。保持 Usage Worker 和事实接收服务运行，未知用量留待对账。

Drain 超时保持拒绝新领取，核对执行状态后显式 resume。取消请求成功后继续观察任务终态、Execution 和结算，不将网络超时视为操作未执行。

## 可复现验收

Windows 执行 `apps/agent/tests/integration/phase4_container_acceptance.py`，显式选择独立 `shenzhi-phase4-*` 网络和 PostgreSQL 容器。脚本复用应用依赖镜像、只读挂载当前源码，使用 production Admin 镜像验证静态资源、可信入口、Cookie、Host / 跨站拒绝及重启。可指定隔离 SSH 镜像验证公钥隧道与关闭失效。全部凭据为临时测试值，脚本仅删除自身创建的容器。

独立数据库 `phase3accept` 用于迁移及管理回归。两库结算回归要求显式选择 `shenzhi_a_line_*` 测试数据库，测试使用随机 Schema。生产数据库和运行 Key 不用于故障注入。

真实外部 Provider 验收需要明确提供的专用非生产凭据。本机替身及隔离证据不能替代现场真实凭据轮换、生产 SSH 用户和公开入口验证。GitHub Actions 配置需在后续授权推送后观察实际运行结果，平台分支保护另行核验。
