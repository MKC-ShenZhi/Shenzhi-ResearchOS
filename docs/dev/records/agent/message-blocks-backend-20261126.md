# Backend 结构化消息适配验证

日期：2026-11-26。分支：`feat/agent-message-blocks`。基线：`f334fa1`。未 commit。

## 实现范围

- 在现有 Gateway、SSE、Session Repository 链路中传递并保存完整 `message`，复用共享消息协议。
- `result.message` 与历史 `turns[].message` 保留同一个原始 JSON；不重排 Blocks/References，不修改正文、系统字段、metadata，不把 References 转成旧来源格式。
- 首次执行、运行中断后的恢复、完成后的重放、重试、无状态兼容接口、v2 SSE 均覆盖。
- 旧记录保留 `message=null`，原正文、报告、来源与 transcript 继续可读。
- 新增 `029_agent_message` 迁移。新 Backend 部署前须先执行迁移；没有操作现有业务数据库。
- Web Client、Feature 和 Renderer 未改。

当前维护约定见 [消息 Blocks](../../../agent/message-blocks.md) 和 [会话持久化](../../../agent/session-persistence.md)。

## 检查与结果

使用 Backend 现有 `uv.lock`、Python 3.12.13，通过 `uv run --locked --with pytest --with aiosqlite` 运行测试。依赖清单和锁文件未变更。异步测试在沙箱外运行，避免 Windows 沙箱的本地 socketpair 阻塞。

| 测试范围 | 结果 |
| --- | --- |
| 新增消息测试、Session、SSE 尾部/重试/API、Gateway、Timeline、附件回归 | 73 passed、3 skipped、31 subtests passed |
| 现有 PostgreSQL 会话持久化/幂等/租约测试 `test_agent_persistence.py` | 12 passed |
| 隔离 PostgreSQL 从空库升级到 `029_agent_message` | 通过 |
| `git diff --check` | 通过 |

3 个跳过项来自原附件测试未配置 `CHAT_DATABASE_URL`；新增消息 PostgreSQL 测试全部实际执行。原 PostgreSQL 会话测试另行显式配置测试库执行，未跳过。

## 一致性证据

新增 `test_agent_message_blocks.py` 检查 Gateway v1/v2 和产品 HTTP/SSE/历史读取，逐字段比较完整消息，包含：

- 多个 Markdown 块及原始顺序、表格、代码、公式、中文、Unicode、CRLF、尾部空格。
- 重复引用、引用数组顺序、作者顺序、显式 `null`、省略字段和嵌套 metadata。
- 所有 SSE 续接偏移、清除缓存后重放、活跃投影恢复、多个尝试及旧格式最终尝试。
- 报告没有快照时使用同一尝试的 `message_end`；冲突、非法引用、状态不符和缺少最终快照时不落库、不发送成功 result。
- 调用方及订阅者修改返回对象时，内存存储和后续 SSE 重放不受影响；owner 隔离仍有效。

新增 `test_agent_message_postgres.py` 在专用 PostgreSQL 16 容器中执行四项测试：

1. 真实投影写入 JSONB，直接读取数据库行核对内容；丢弃 Backend 缓存和数据库连接后，用新 Repository 经历史 HTTP 接口及 SSE 重放再次核对完整消息。
2. 五种终态完整往返，旧记录保持 SQL NULL，旧正文不变。
3. 无效消息不导致部分终态写入。
4. 在独立 schema 创建迁移前数据，实际运行 `029_agent_message.upgrade()`，核对旧正文、换行和记录 ID 不变，新列保持 NULL。

临时数据库仅绑定本机随机端口，使用内存数据目录；验证结束后停止。未调用真实 LLM 或上游知识服务。

重跑新增 PostgreSQL 测试时，须将 `TEST_AGENT_MESSAGE_DATABASE_URL` 指向已应用迁移的独立测试库，再在 `apps/backend` 执行：

```powershell
uv run --locked --with pytest --with aiosqlite python -m pytest tests/test_agent_message_blocks.py tests/test_agent_message_postgres.py -q
```
