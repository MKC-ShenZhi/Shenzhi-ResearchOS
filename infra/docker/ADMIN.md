# Admin 生产 SSH 隧道入口

默认基础/生产 Compose 不启动 Admin。开发仍使用 `compose.dev.yml`；生产管理入口使用 `compose.yml` + `compose.prod.yml` + `compose.admin.yml`，不能叠加开发 override。先阅读 [部署约定](../../docs/engineering/deployment.md#四admin-管理入口ssh-密钥与隧道)。

1. 在本地 `.env` 或部署环境配置 `ADMIN_TUNNEL_PRINCIPAL`（稳定身份）、`ADMIN_TUNNEL_SESSION_SECRET`（至少32字符随机值）、`ADMIN_ENTRY_SECRET_PATH`（权限受控文件的绝对路径）。入口文件内容为64位小写十六进制随机值，与 Session Secret 不同；不要提交这些值。
2. 在 Backend、Agent API 的 env 文件配置相同、独立的 `AGENT_MANAGEMENT_TOKEN`。不配置时目录返回503，其他管理功能不因此失效。API/Worker 使用同一模型 Registry 与技能资源；API 的目录不证明 Worker 当前状态。
3. 使用已审核的镜像标签；Admin production 镜像由 `apps/admin/Dockerfile --target production` 构建。
4. 公共反向代理安装 `nginx/public-admin-deny.conf`，禁止发布 Admin 静态文件；Backend 启动保留 `--no-proxy-headers`。仅专用 Nginx 注入入口 secret。
5. 用下列配置顺序启用 admin profile；现有数据库按部署流程备份/迁移，使用共享环境前先核对版本。集成只读目录不需要新管理迁移。

```text
docker compose -f compose.yml -f compose.prod.yml -f compose.admin.yml --profile admin up -d --build --wait admin
```

入口固定宿主 `127.0.0.1:3101`，Admin 与 Backend 共享 network namespace；Nginx 通过容器 loopback:8000 调用 Backend。Nginx 非root、read-only、tmpfs，丢弃 capabilities，不使用 Vite。Backend 重建后需重新关联 Admin 容器，不能只保留旧网络命名空间。该 override 必须显式排在生产 override 之后，以设置隧道专用 Session Secret。

SSH 命令与密钥管理见部署约定。服务器及管理员设备两端均只绑定 loopback，不用 `ssh -g`。Nginx 和 Backend 校验 Host/Origin/跨站请求；Backend 每次校验入口 secret 和 Cookie。SSH 自身不传递 HTTP 身份；审计使用固定 `ssh-admin:<principal>`。退出清 Cookie，关闭隧道结束入口访问。

上线验收须覆盖真实 SSH、PermitOpen、公共代理路径阻断、跨站拒绝、关隧道失效，以及现有套餐发布/分配/审计。仓库实现及本地验收不等于真实服务器已部署。

并行开发验收使用独立 Compose project、独立 env/secrets、数据库/卷及端口；3101已被占用时不要启动第二套固定管理入口，也不要停止其他任务容器。仅执行 `config`、独立构建或使用测试脚本的随机端口完成检查。
