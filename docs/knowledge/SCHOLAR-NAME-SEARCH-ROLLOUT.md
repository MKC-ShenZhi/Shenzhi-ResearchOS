# 落地方案-学者姓名检索

## 一、方案结论

学者姓名检索采用“上游能力优先、ShenZhi 最小兜底”的方案。

长期由知识底座在现有 Scholar Search 中原生支持中文名、英文名和已确认别名，并为同一学者返回稳定的 `scholar_id`。在上游能力落地前，ShenZhi 只在现有 `KnowledgeService.search_scholars()` 中维护极小、人工确认且只做精确匹配的临时映射，然后继续调用现有 Knowledge Adapter。

当前已确认：知识底座 URL 和调用环境可用；英文名 `Kaiming He` 可以命中，中文名 `何恺明` 返回空结果。因此问题是上游姓名召回能力暂不完整，不是环境缺失、BFF 故障或前端展示问题。

## 二、设计原则

1. **保持调用边界不变。** Browser → Next.js BFF → ShenZhi FastAPI → Knowledge Adapter → 知识底座。
2. **优先推动上游完善。** 中文名与英文别名应最终由知识底座统一索引，ShenZhi 不长期维护第二套学者身份系统。
3. **临时方案足够小。** 映射和解析函数放在现有 Knowledge Service 文件内，不为单个映射新增层级、数据表或管理系统。
4. **只做确定性改写。** 仅精确命中已审核映射时改写；未知中文名原样传给上游，不翻译、不猜测、不自动绑定实体。
5. **公共契约不变。** 不新增 `matched_by`、`normalized_query` 等未经上游确认的响应字段，不改变 Search、Detail 和错误响应结构。
6. **复用统一基础设施。** 不新建 logger、request-id、中间件、异常框架、重试机制、日志库或审计库。

## 三、范围与边界

### 本次范围

- 为已人工确认的高频中文姓名提供精确英文查询映射。
- 保持现有 Scholar Search → Detail 的 `scholar_id` 传递和页面行为。
- 补充映射命中、未知姓名、英文姓名以及上游错误的自动化测试。
- 与知识底座组确认原生别名检索的契约和排期，上游支持后删除本地映射。

### 明确不做

- 不新增数据库表、migration、repository、管理页面或审核工作流。
- 不引入 LLM、机器翻译、拼音转换、模糊匹配或新的第三方依赖。
- 不在前端、BFF 或 Knowledge Integration Client 中维护姓名规则。
- 不新增 feature flag、灰度平台、独立审计记录或产品埋点。
- 不记录用户输入的原姓名、改写后的姓名或请求正文。
- 不修改论文、图谱、Funding、Scholar Detail 等既有契约。
- 不承诺 `author_id` 片段搜索、同名消歧或上游尚未确认的能力。

## 四、轻量实现框架

```text
用户输入姓名
→ 现有 Next.js BFF
→ 现有 Knowledge API
→ KnowledgeService.search_scholars()
   ├─ 精确命中临时映射：构造新请求，替换 query
   └─ 未命中：保持原 query
→ 现有 Knowledge Adapter / Client
→ 知识底座 Scholar Search
→ 原样返回现有 ScholarSearchResponse
```

临时规则属于产品侧的确定性业务判断，因此放在 Backend Service；Adapter 继续负责上游协议适配，Client 继续负责 HTTP 与外部错误转换。前端和 BFF 不感知改写。

映射当前只有一项，直接由 Git 评审和历史追踪即可。只有当映射数量、更新频率或治理要求真实增长时，才重新评估配置文件或持久化管理能力。

## 五、统一 Error & Logging 复用

本方案完全复用 `docs/logging/README.md` 定义并已落地的统一能力：

- Next.js BFF 生成或透传 `X-Request-ID`；
- FastAPI 通过 ContextVar 保存 `request_id`，HTTP 中间件记录状态与耗时；
- Knowledge Client 继续记录 `knowledge.request.completed` / `knowledge.request.failed`；
- `KnowledgeIntegrationError` 继续转换为 `KnowledgeServiceError`，API 再按现有 Knowledge Error Contract 返回；
- 超时、限流、上游不可用和契约异常保持原有 code、HTTP status 与 retryable 语义。

姓名改写不是新的外部调用边界，不增加 `try/except` 和业务日志。统一日志明确禁止记录用户 Query 原文，因此不记录原姓名、改写后姓名或映射内容，也不为了统计命中率扩展敏感日志字段。排障使用已有 `request_id`、`provider`、`operation`、`status_code`、`duration_ms`、`error_type` 和 `error_code`。

## 六、阶段与退出条件

### 阶段 1：ShenZhi 最小兜底

在现有 Knowledge Service 中加入已审核的不可变映射和私有解析函数；增加单元测试，确认中文映射、英文透传、未知中文透传和错误语义均符合预期。

### 阶段 2：知识底座原生支持

知识底座在现有 Scholar Search 中提供正式别名召回。同一学者的中文名和英文名应返回相同 `scholar_id`，空结果仍返回正常的空集合，上游错误仍按既有契约表达。

### 阶段 3：删除临时映射

上游能力在联调和回归测试通过后，删除 ShenZhi 本地映射与对应改写测试，保留端到端中文姓名用例。无需数据迁移或功能开关，回滚只需恢复一个小型代码提交。

## 七、具体实现

### 7.1 修改位置

仅修改现有文件：

```text
apps/backend/app/services/knowledge/service.py
apps/backend/tests/test_knowledge_entities.py
```

不创建新的 Service、Resolver、Repository、Integration 或配置层。

### 7.2 映射与解析

首个已确认映射：

```python
_SCHOLAR_QUERY_ALIASES = {
    '何恺明': 'Kaiming He',
}


def _resolve_scholar_query(query: str) -> str:
    return _SCHOLAR_QUERY_ALIASES.get(query, query)
```

`KnowledgeService.search_scholars()` 解析后构造新的 `ScholarSearchRequest`，保留原 `limit` 和 `offset`，再调用现有 Adapter。不得修改传入的 Pydantic 对象，也不得绕过 Adapter 直接调用 Client。

已有 Schema 负责 Query 的 trim、长度和分页校验，本方案不重复实现这些规则。

### 7.3 接口与字段

ShenZhi 接口保持不变：

```text
GET /api/v1/knowledge/scholars/search?q={query}&limit=20&offset=0
GET /api/v1/knowledge/scholars/{scholarId}
```

上游接口保持不变：

```text
GET /api/retrieval/scholars/search?q={query}&limit=20&offset=0
GET /api/retrieval/scholars/{scholar_id}
```

请求、响应和 Domain 字段均不扩展。错误码继续使用：

```text
INVALID_ARGUMENT
NOT_FOUND
RATE_LIMITED
UPSTREAM_UNAVAILABLE
TIMEOUT
CONTRACT_VIOLATION
```

## 八、测试与验收

### 8.1 自动化测试

| 用例 | 预期结果 |
| --- | --- |
| `何恺明` 搜索 | Adapter 收到 `Kaiming He`，分页参数不变 |
| `Kaiming He` 搜索 | Query 原样透传 |
| 未配置的中文姓名 | Query 原样透传，不猜测英文名 |
| 映射后的上游空结果 | 返回现有空结果，不伪造 Scholar |
| 映射后的上游超时/限流/不可用 | 保持现有错误码、状态码和 retryable 语义 |
| Search 返回 Scholar | Detail 使用 Search 返回的 opaque `scholar_id` |
| 日志检查 | 不出现原姓名、改写姓名或请求正文 |

执行范围：

```text
Backend Scholar 单元测试
Backend Knowledge 核心与 Query 回归测试
Web Knowledge 回归测试
TypeScript 类型检查
```

### 8.2 联调验收

当前真实接口基线：

```text
Geoffrey Hinton → 1 条结果
Kaiming He      → 1 条结果
何恺明           → 0 条结果
Kaiming He 详情  → 11 篇论文、30 位合作学者
```

实现后需要验证：中文输入经 ShenZhi 返回与英文输入相同的 `scholar_id`，详情页正常打开；英文检索、未知姓名空结果和其他 Knowledge 能力无回归。

### 8.3 人工浏览器检查

1. 打开学者库页面，搜索 `何恺明`，确认出现 `Kaiming He`。
2. 打开该学者详情，确认 URL 使用 Search 返回的 `scholar_id`，论文和合作学者可见。
3. 搜索 `Kaiming He`，确认结果与中文搜索指向同一 `scholar_id`。
4. 搜索一个未配置且上游不存在的中文姓名，确认展示空结果，不出现猜测或错误学者。
5. 在 Network 中检查 BFF 响应包含 `X-Request-ID`；服务端日志可按该 ID 关联，但不包含搜索姓名。

## 九、方案变更触发条件

只有出现下列真实需求时才扩大设计：映射规模已无法安全代码评审、需要非开发人员高频维护、需要多来源冲突治理，或知识底座明确无法承担长期别名召回。在此之前保持当前两项改动，不提前建设别名平台。
