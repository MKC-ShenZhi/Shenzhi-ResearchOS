# Docker 新依赖与 Billing 迁移补齐

用户报告订阅组件 `Can't resolve 'qrcode'`。仓库 package.json/锁文件已有依赖，
但 Web 运行的是旧镜像，源码已同步而 node_modules 尚未更新。
Backend 同样缺少新增支付宝 SDK，旧镜像内迁移目录只到 028。

处理：

- 使用 dev Compose `up -d --build --no-deps web` 重建并更新 Web。
- 构建 Backend 镜像，通过 `run --rm --no-deps backend-migrate` 成功执行 028 → 029。
- 更新 Backend，并重新关联共享其网络命名空间的 Admin；未更改 Admin 认证方案。
- 保留全部持久卷及现有业务数据；未创建测试订单或修改用户权益。
- Docker README 补充 Module not found 的依赖重建说明，未改动用户本轮修改的 VS Code 任务配置。

验证：

- Web 容器 `require.resolve('qrcode')` 成功，版本 1.5.4。
- 订阅页实际请求 HTTP 200，无 Module not found；Chrome 中正常显示登录提示及设置 Tab。
- Backend 支付宝 SDK 3.7.1467 可导入，Alembic 当前版本 `029_billing (head)`。
- 使用内部 BFF 凭据和无持久化的合成检查身份，只读请求 Billing plans/subscription/orders 均返回 200。
- Web、Backend、Admin、Payment 和 PostgreSQL 健康检查正常。

这是运行环境未随新依赖/迁移更新的问题，无需删除数据库卷或移除二维码功能。
