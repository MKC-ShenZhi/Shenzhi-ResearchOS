# Docker 初始化与迁移 Smoke 维护修复

基线：`de4c96aadfd758ab533665d50f305b7d9487d04e`；分支：`chore/docker-compose-infra`。

## 修复范围

- `prepare-env.py` 将缺失/空白值与非空值分开处理。可导入空值从本机配置补齐，非空 Docker 值保留；
  共享凭据、audience/issuer 优先复用 Docker 中的有效值，配置冲突明确报错，不输出值。
- 签名文件不生成、不轮换。空路径先复用已有副本，再考虑有效本机路径；校验文件存在、可读、非空且为普通文件。
  V2 原有校验继续生效，缺少文件不降低准入要求。Provider 空覆盖项无有效本机值时保持未设置。
- 所有校验先完成，再暂存输出并替换；写入失败恢复已替换文件，回滚也失败时保留原文件备份供人工恢复。
  内容未变不重写文件。临时目录测试覆盖幂等性、校验失败及 I/O 失败回滚。
- `auth_migrations.py` 共享原认证迁移的 SQL 排序与 checksum 规则（UTF-8 BOM、通用换行、SHA-256）。
  `migrate.py` 只复用发现/计算逻辑，不修改迁移 SQL、数据库 Schema 或历史账本。
- `smoke.py` 动态核对文件名和账本 checksum，明确报告缺失、额外记录或 checksum 不一致，不固定迁移数量。

## 测试与运行验证

- `python -m unittest discover -s infra/docker/tests -v`：24 项通过；只使用临时目录、虚构凭据和合成 SQL。
  涵盖首次初始化、空值补全、所有角色 Token、有效值保留、重复执行、跨服务冲突、签名缺失/空值/有效路径、
  校验失败与发布失败的数据保护；涵盖三个/四个迁移、缺失/额外账本、checksum 不匹配和 BOM/换行兼容。
- 初次测试受 Windows 沙箱临时目录访问权限限制；在允许临时目录访问的执行环境中复跑通过。
- base/dev/prod 三套 `docker compose ... config --quiet` 通过，Python compileall 与 `git diff --check` 通过。
- 现有镜像内原 Smoke Test `docker compose ... exec -T backend python /opt/docker/smoke.py --full` 通过。
- 更新脚本只读挂载到一次性容器运行：
  `docker compose ... run --rm --no-deps -T --volume <仓库绝对路径>/infra/docker/scripts:/opt/review-scripts:ro backend python /opt/review-scripts/smoke.py --full`。
  动态迁移核对、Web/BFF/Backend/Agent 通信、认证端点与内部凭据拒绝检查全部通过；未指定 `--write-probe`。
- 检查前后原生/Docker 环境文件和签名文件的内容摘要一致，现有服务容器 ID 和启动时间一致。

未重建镜像、重启现有服务、执行数据库迁移或修改已有持久化数据；未改 Compose、Profiles、Dockerfile、
Admission、Worker Protocol、生产部署策略、业务 API 或前端功能。真实模型/邮件/登录验收不在此次修复范围。
