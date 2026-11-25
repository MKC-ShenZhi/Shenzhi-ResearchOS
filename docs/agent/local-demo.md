# M1 本地演示已退役

旧版 M1 本地 Mock 演示依赖已退役的 Agent V1 Worker。本仓库当前不提供可运行的 M1 Mock 启动器；不要按历史验收记录中的命令启动它。

后续本地联调应使用独立 Backend / Agent 数据库、配置 V2 Gateway/Service/Worker/Fact Reader 角色凭据、完成 V2 准入设置和迁移后，分别启动 Web、Backend、Agent API 与 V2 Worker。Agent V2 只会领取具有有效 metering profile 的 Task；没有完整隔离的 V2 Mock admission fixture 时，请勿连接开发或生产数据库进行演示。

历史演示记录保留作审计背景，不构成当前代码可运行或生产验收通过的证据。双库 V1 排空和外部调用方日志审计仍应按 [开发与退役审计说明](development.md) 单独执行；退役代码不会删除任何历史 Task、Run、Turn 或事件。
