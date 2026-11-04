# 会议 DDL 自动同步设计与维护

## 目标与边界

在现有会议 DDL 功能上接通上游 YAML → 清洗校验 → 数据库当前快照 → API 缓存 → 页面。保留时区换算、当届选择、排序、筛选与已有 status 值；新增 needs_update 字段只用于展示。Rebuttal / decision 字段显式忽略，不进入公开契约。不新增依赖。

## 模块职责

- integrations/conferences/client.py：GitHub HTTP、超时、大小限制、内存 tar 成员读取；不做业务写库。
- services/conferences_source.py：离线 YAML 归一化与完整目录校验；发布命令和在线同步共用。
- models/conference_snapshot.py + services/conferences_repository.py：当前快照与调度元信息持久化、异步缓存加载。
- services/conferences_sync.py：版本比较、到期判断、替换保护、同步编排。
- services/conferences_cli.py：本地发布 / check / 手动同步 / dry-run。
- 原 HomeFeedScheduler：新增独立开关的会议任务，不更名、不建立第二个常驻调度循环。

## 存储与性能

conference_snapshots 通过 id=1 约束只保存当前一份 JSONB，避免每天复制历史全量数据。保存 snapshot_id、上游 SHA、资料日期、同步时间、成功检查时间、尝试时间。SHA 未变只更新小字段；失败仅更新尝试时间，原 payload 保留。需要回滚时可关闭开关，再用经核验的上游版本恢复数据；本次不实现历史版本后台。

进程缓存保存已校验并完成时区转换的目录，每 5 分钟只读取 snapshot_id；版本变化才加载并解析整份 JSON。并发刷新用 asyncio.Lock 合并；数据库读取有 3 秒超时。数据库暂时不可用时优先保留最近一次已验证目录，冷启动才使用打包快照，避免瞬间退回更旧数据。快照 ID 包含上游 SHA 和日期，因此上游仅更新元信息时也会刷新。

在线下载只发版本与压缩包请求，不按会议逐条请求。下载上限 50 MiB，YAML 单文件 2 MiB、总量 20 MiB，tar 声明展开量 150 MiB / 10000 成员；拒绝路径穿越、链接、重复资料文件。只读取 conference/types.yml 和 conference/*/*.yml，不解压到磁盘。YAML 解析放在线程中避免阻塞异步请求。

## 一致性与错误处理

手动与定时写入共用 Postgres advisory lock；检查到期和写入在持锁期间执行。约每天检查一次（23 小时间隔，给轮询、下载和缓存刷新留余量），失败后至少 1 小时再尝试，尝试时间存数据库，进程重启不丢退避。同步异常被调度器隔离，不阻断首页任务。

写入前使用与打包快照相同的 schema、日期/时区/重复 ID/分类/年份校验。会议数量下降超过 10% 或用户关注 ID 消失，拒绝写入。消失 ID 也记录日志。已知 ds-dcc → cg-dcc、se-eusipco → cg-eusipco 由 021 迁移，合并重复关注并保留记录；合并不可逆，downgrade 不推测用户原选择。022 建立当前快照表。必须与新快照同批上线。

## 展示

/submit 显示资料日期和来源。closed 且最后投稿截止距今超过 365 天，新增 needs_update=true，卡片显示“待更新”及上游链接；不把它推断成会议停办，也不改变原筛选状态。此展示按交接建议实现，评审可调整文案。

## 验证与上线

离线测试不访问 GitHub：覆盖归一化、新/未知字段、时间类型、压缩包防护、SHA 未变、替换成功、数量骤减、关注消失、超时、失败退避、空库兜底、缓存换版和调度隔离。迁移及实际写库使用独立本地 PostgreSQL 测试库。

上线前执行迁移；确认生产可访问 api.github.com 和 codeload.github.com。长驻后端配置 CONFERENCE_SYNC_ENABLED=true；Vercel 使用下节 HTTP Cron，不能靠进程内循环保证执行。两个环境复用相同业务服务。GitHub 共享 IP 限流时可配置服务端只读 CONFERENCE_GITHUB_TOKEN，不应写入代码或前端。

## 当前验证结果

2026-11-03：41 项会议测试、迁移和实际 PostgreSQL 写读验证、6 项调度器数据库测试、11 项前端会议测试及类型检查通过。完整后端测试的 7 处非会议失败在原始 dev 上复现。匿名 GitHub API 当前限流；真实压缩包及写库验证使用已拉取的精确 SHA 元信息，不冒充 latest API 成功。正常检查间隔为 23 小时，已为 10 分钟轮询、下载与 5 分钟缓存刷新预留余量。已完成本地浏览器搜索、空结果、待更新提示、匿名关注登录拦截和手机宽度验收，无脚本错误或横向溢出。

2026-11-04 补充：配置仅后端使用的本地 GitHub Token 后，真实应用启动自动同步及九项保护场景合计 10 项验收通过；真实最新提交为 aa5675e7e54ffde41032f97723cf5e52a4cc6844。采用测试进程加速轮询及独立测试库时间模拟，未进行连续 24 小时耐久运行或生产上线。

## 审查后补充

2026-11-04 修复发布与关注竞态、页面长期打开缺少定时刷新、压缩包元数据绕过解压预算问题，并将替换校验移到线程。新增短时发布锁不跨网络调用；查询页面每五分钟刷新。43 项离线测试、真实 PostgreSQL 竞态和 12 项自动运行/缓存检查通过。详见 REVIEW-2026-11-04.md；该结果不等同生产负载或 24 小时耐久验收。

## Vercel HTTP Cron（2026-11-04）

后端 vercel.json 注册 GET /api/v1/internal/conference-sync，每天 01:00 UTC（北京时间 09:00）触发一次；不在 Web 项目重复配置。沿用 maintenance 路由的 CRON_SECRET 恒时比较鉴权。请求内 await ConferenceSync.run()，不依赖 lifespan 或响应后的后台任务；服务层的数据库锁、SHA 跳过、校验、持久退避、快照保护全部共用。VERCEL=1 时会议进程内循环不启用，长驻服务器继续复用原调度器；未改动其他首页任务开关。

部署清单：

1. 在目标数据库执行 `uv run --env-file .env alembic -c alembic.ini upgrade head`（021/022），先确认目标库并按团队数据库变更流程操作。
2. 后端 Vercel 项目配置 CHAT_DATABASE_URL、随机且至少 16 字符的 CRON_SECRET、CONFERENCE_CRON_ENABLED=true；建议配置只读 CONFERENCE_GITHUB_TOKEN。CRON_SECRET 只放服务端环境变量，不提交代码。Vercel 自动在 Cron 请求附带 Authorization: Bearer <CRON_SECRET>。
3. CONFERENCE_SYNC_ENABLED=false；不要依赖临时实例的后台循环。配置变更后部署。
4. 自动 Cron 只对 Production 部署生效；分支 Preview 不会自动定时执行。确认项目的 Production Branch 实际对应本次验收分支（例如团队配置的 dev），不是一律假设 main。PR 预览可用受密钥保护的请求手动验收。
5. 在后端项目 Cron Jobs 面板确认任务已注册，手动 Run 并检查 HTTP 200 和 data.status；updated / unchanged 为成功检查，locked / not-due / retry-delayed 为安全跳过。确认数据库 SHA、checked_at，以及 /submit 五分钟缓存刷新后的资料日期。缺密钥、关开关、缺数据库返回非成功；执行异常503、超时504。日志不向响应泄露异常详情。
6. 观察下一次实际定时执行记录后才能签线上自动运行验收；本地测试不能证明平台已经注册并执行。

整个请求有 240 秒预算，低于配置的 300 秒函数上限；下载另有180秒预算。失败保留旧快照；若平台强制中断则由数据库连接关闭释放事务锁，尝试时间使后续请求遵守退避。响应不缓存。

调度边界：默认每日配置兼容 Hobby 的每日频率限制，但平台不是精确时钟，也不会自动重试失败的 Cron。服务层的一小时退避只是允许一小时后重试，不会自行产生请求。默认失败后下一次定时尝试可能到次日；可在面板人工重跑。若验收要求失败自动一小时内恢复或严格上游滞后≤24小时，应在支持小时级 Cron 的套餐确认后把 schedule 改为 `0 * * * *`，仍由23小时成功间隔和一小时失败退避避免多余拉取，或由团队现有外部调度器按小时调用同一受保护入口。不能把每日一次的基线配置宣称为严格24小时SLA，也不能未经确认使用小时表达式导致 Hobby 部署失败。

官方依据：https://vercel.com/docs/cron-jobs/quickstart 、https://vercel.com/docs/cron-jobs/manage-cron-jobs 、https://vercel.com/docs/cron-jobs/usage-and-pricing 。不新增依赖，不使用 GitHub Actions 发布快照。

本地验证：新增6项HTTP Cron测试，会议相关共运行50项，49通过、1项跳过（依赖可选数据库环境）；覆盖鉴权拒绝、缺配置拒绝、共享服务的成功与跳过状态、异常不泄露、请求超时取消、Vercel进程循环禁用和调度配置。未进行本次Vercel云端部署或平台定时执行验收。
