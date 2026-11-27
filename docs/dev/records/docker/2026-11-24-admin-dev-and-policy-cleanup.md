# Docker Admin 开发接入与旧 Policy 清理

日期：2026-11-24。当前分支修改，未提交；取消 init-dev.py 方案。

## 修改范围

- 删除旧 Free 演示 JSON、固定 DeepSeek 预算 JSON 及强绑定的 free_policy.py 生成 CLI。
- 删除该生成器专用测试；PostgreSQL 测试改为独立历史 task_fixed Free fixture，继续验证旧数据读取和消费展示。
- 正式 Basic/Pro/Research 生成、发布、分配与预算/计量代码保留；不删除数据库历史记录。维护文档移除旧配置引用，旧实施记录保留并标注失效。
- Admin 新增开发 Dockerfile 和 pnpm 构建脚本白名单（仅 esbuild），不新增依赖、不修改锁文件、不新增启动包装脚本。
- Admin 只在 compose.dev.yml 的 full profile 定义，共享 Backend 网络命名空间；宿主仅发布 127.0.0.1:3101，代理目标 127.0.0.1:8000。Backend local-only 和 --no-proxy-headers 保留。
- Vite 仅在显式 Docker development 模式接受非 loopback 容器入口，校验实际 Host/Origin 与 Sec-Fetch-Site，移除转发 Header。原生模式继续要求 loopback。
- 开发账号 shenzhi / shenzhi-dev 只由开发 override 注入。prepare-env.py 生成并幂等保留 ADMIN_DEV_SESSION_SECRET；生产 override 清空管理认证配置，Backend 在非 development 环境拒绝开发密码。

## 启动命令

从仓库根目录执行：

```powershell
python infra/docker/prepare-env.py
cd infra/docker
docker compose -f compose.yml -f compose.dev.yml --profile full up -d --build --wait
```

访问 http://localhost:3101 。若首次配置需要导入已有原生应用环境，使用 prepare-env.py --from-local；这不会导入 Admin 密码。

## 实际验证

1. Docker Desktop Engine 29.9.2：full 构建并启动成功，Web、Backend、Agent、Admin 均通过现有健康检查；迁移服务正常退出。保留原数据卷。
2. 现有 smoke.py --full 通过：Web/BFF/Backend、认证迁移账本、Agent 配置和 V2 凭据隔离。未调用真实模型/搜索/邮件。
3. 宿主 loopback HTTP 实测：默认开发账号登录、会话查询、用户/模型能力/套餐查询和退出正常；错误密码拒绝。未修改现有用户权益和正式套餐。
4. 宿主 HTTP 实测：错误 Host、跨站 Origin、cross-site Fetch Metadata 拒绝；直接访问 Backend 并伪造转发 Header 仍拒绝；缺少 X-Admin-Request 的写操作拒绝。普通 Web 的原始和编码 Admin 路径均返回 404。
5. 新增真实 Admin HTTP 路由测试，使用隔离 SQLite 数据库及合成 Agent 能力目录：上传 JSON 请求、正式发布、查询三档套餐、分配预览、确认分配、重复请求及审计通过。服务与 ORM 事务不 mock。此验证不等同于浏览器文件选择器的手动验收。
6. 本机 Docker PostgreSQL 新建两座唯一 shenzhi_a_line_admin_* 临时测试库：历史 Free 兼容两项、新增 HTTP 发布分配一项，共 3 项通过。测试后只删除本次新建的临时库。
7. Admin pnpm build 通过；Admin 认证/路由测试 12 项通过；Backend 窗口/授权测试 5 项通过；Docker 配置与迁移测试 26 项通过（包含随机 Secret 和重复生成保护）。
8. Compose 配置解析断言通过：base/prod 无 Admin 服务、3101 端口和开发默认凭据；prod 管理认证禁用且凭据清空；dev 保留 local-only、随机 Secret 和所有宿主 loopback 映射。未启动生产部署。

## 已有测试失败

运行 Agent test_formal_plans.py 与 test_a_line_persistence.py：45 项通过、2 项失败（新增 HTTP 测试随后单独通过）。两项失败使用 HEAD 原版套餐测试再次复现，未扩大范围修改：

- test_dynamic_missing_profile_or_input_room_fails_before_reservation：断言期待 MODEL_INPUT_BUDGET_EXHAUSTED，现有实现返回 QUOTA_EXHAUSTED。
- test_sync_settlement_requires_backend_ack_and_keeps_original_outbox：现有测试期待 GateDenied，实际未抛出。

Windows 沙箱首次测试遇到临时目录/uv 缓存权限限制；允许本机工具访问后，上述相关测试已重跑通过。首次 Admin 镜像安装被 pnpm 11 的 esbuild 构建脚本门禁阻止，已以显式单依赖白名单解决并完成实际构建。
