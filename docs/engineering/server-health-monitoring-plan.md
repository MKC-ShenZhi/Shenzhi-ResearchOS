# Linux 服务器健康巡检与飞书告警（方案 A）

P0 采用 **Bash + cron**：

- 脚本：`scripts/ops/health-report.sh`（`probe`：新告警、持续告警、**恢复通知**）
- 配置：`scripts/ops/ops.env.example`
- 测试群验通：`scripts/verify_feishu_webhook.py`（`docs/logging/README.md` §15）

飞书 Wiki 有完整步骤；正式机摘要见 [deployment.md](./deployment.md#正式服务器宿主机巡检与飞书告警)。