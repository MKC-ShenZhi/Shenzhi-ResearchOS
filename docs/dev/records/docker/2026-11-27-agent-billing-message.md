# 合并后的 Agent Platform Docker 开发运行

基于 `feat/agent-platform` 的 `8e3e6f8e`，使用 `compose.yml` + `compose.dev.yml`、`full` profile。

## 执行结果

- 运行 prepare-env.py --from-local，保留已有 Docker 环境值和服务凭据。
- 更新前 Backend 为 029_billing、Agent 为 0003_agent_metering；业务 running Turn 和 Agent pending/running Run 均为 0。
- 构建全部开发镜像，停止应用进程后将 PostgreSQL 全库逻辑备份保存至本地忽略目录 `.cache/docker-backups/pre-message-merge-20261127.sql`。备份包含敏感业务数据，未纳入版本控制，未执行恢复演练。
- 重新创建 Full 服务，保留已有数据卷；Backend 应用 029_agent_message 和 030_merge_billing_message，Agent 迁移无新增步骤。
- Web、Backend、Agent API、Admin、Postgres、Payment 健康检查通过，两种 Worker 均保持运行，迁移容器退出码为 0。
- Full Smoke Test 通过 Web/BFF/Backend、认证表、管理接口隔离、Agent 配置读取及 V2 角色隔离。
- `/agents` 与 `/settings?tab=subscription` 返回 HTTP 200；数据库版本为 030_merge_billing_message，agent_turns.message 为 JSONB。

## 验收脚本修正

Agent V2 缺少 Service 凭据时按现有 role 校验返回 403；将 Smoke Test 中旧的 401 断言修正为 403，未修改认证行为。重建 Backend 后重复 Full Smoke Test 通过。Docker 工具单元测试共 27 项通过；本机沙箱临时目录权限问题通过为测试指定仓库内独立临时目录解决。

没有执行真实模型、搜索、邮件、支付或新任务，也没有运行浏览器视觉验收。未启动持续 Compose Watch，后续源码同步需单独启动。

## 后续开发入口

从 infra/docker 执行：

```powershell
$dc = @('-f', 'compose.yml', '-f', 'compose.dev.yml', '--profile', 'full')
docker compose @dc ps -a
docker compose @dc watch --no-up web admin
```

Web 使用本机 3300 端口，Admin 使用本机 3101 端口。Agent 源码变化后重启 agent-api、agent-worker、agent-usage-worker；依赖或镜像内文件变化需重新构建对应镜像。
