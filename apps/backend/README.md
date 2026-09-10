# ShenZhi FastAPI

Chat、论文检索、模型流、联网搜索、附件解析及 Knowledge Capability。浏览器只访问 Next.js 的 `/api/v1` BFF。

```bash
cd apps/backend
uv sync
cp .env.example .env

# Configure provider/search keys before starting.
# Missing keys produce explicit errors, never mock answers.
uv run uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000

# Validate backend code and tests.
uv run python -m compileall app
uv run python -m unittest discover -s tests -v
```

Web 设置：

```text
BUSINESS_BACKEND_URL=http://127.0.0.1:8000
```

两端配置相同 `BACKEND_BFF_SECRET`；后端只允许私网/BFF 访问，不能直接暴露公网。

未配置 Secret 时默认拒绝；仅 loopback 本地开发可在两端显式设置：

```text
BACKEND_ALLOW_INSECURE_LOCAL_BFF=true
```

## Knowledge Capability

Knowledge Base 是外部 Research Capability。FastAPI 后端统一通过
`app/integrations/knowledge/` 接入，调用链固定为：

```text
FastAPI API → app/services/knowledge.py → app/integrations/knowledge → 上游知识底座科研组 API
```

当前只承诺三条 ShenZhi-owned Capability API：

```text
POST /api/v1/knowledge/search
GET  /api/v1/knowledge/paper?paperId=...
GET  /api/v1/knowledge/graph?paperId=...&depth=1
```

Integration 内部职责保持分离：`client.py` 负责上游 HTTP transport，`schemas.py`
描述上游实际字段，`adapter.py` 映射到 ShenZhi Domain Contract，`exceptions.py`
统一上游调用异常。当前上游资源仅限 retrieval search、paper detail、paper graph。

响应使用 `data` envelope 和独立 Knowledge Contract；上游 `paper_id` 是不透明
字符串，且必须来自 retrieval search，不能使用会议列表接口的 `paper_id`。本阶段
不接 Chat Tool、`/api/papers`、multistep 或知识底座认证/收藏接口，也不在 ShenZhi
侧修复上游数据和检索能力。

Contract v0 的核心字段为：Search `results[].id/title/abstract/authors/year/venue/keywords/subjects/score/rank`；
Detail `id/title/abstract/authors/year/venue/doi/pdfUrl/keywords/subjects/citationCount/referenceCount`；
Graph `rootId/nodes/edges`，边使用 `sourceId/targetId/relation`。空字符串归一化为 `null`，
未知引用数保持 `null`，节点和关系类型为开放字符串。错误响应包含
`code/message/retryable/requestId`。Search 请求只使用 `query/topK/yearFrom/yearTo/venue/author/keyword/subject`；
上游的 snake_case 字段只在 Adapter 到 HTTP Client 的边界出现。

`GET /api/v1/knowledge/paper` 只返回知识底座论文详情和 `pdfUrl`，不预先访问 PDF 源站。
用户首次打开 Paper 视图时，站内 PDF.js 才通过受控的
`GET /api/v1/paper-resource/pdf?paperId=...` 同源端点读取字节流，避免科研源站缺少
CORS 响应头导致浏览器拒绝加载。端点只接受可信 `paperId`，不接受任意 URL；Backend
在该端点内复用 `PaperResourceService` 与 Provider 完成校验和流式读取，不持久化或缓存 PDF。
配置项为 `PAPER_RESOURCE_TIMEOUT`（秒）与
`PAPER_MAX_SIZE_MB`（可获取资源大小上限）。

当前仅支持 **单进程 / 单 worker**，Session 与解析后的附件为临时内存数据，重启清空。

Python 环境与依赖统一使用 [uv](https://docs.astral.sh/uv/) 管理。新增依赖使用：

```bash
uv add <package>
```

新增开发依赖使用：

```bash
uv add --dev <package>
```

维护说明：[Chat 架构、协议与配置](../../docs/chat/README.md)。
