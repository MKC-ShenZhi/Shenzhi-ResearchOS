# 落地方案-学者姓名检索

## 一、方案定位

本方案解决学者库中“中文姓名搜索无结果、英文姓名可以命中”的产品问题。当前知识底座服务可访问，英文检索与详情链路正常；问题属于姓名召回与别名匹配能力，不属于 BFF、URL 配置或前端展示故障。

目标是让用户可以使用中文名、英文名、常见姓名变体或稳定 author_id 找到同一个学者，同时保持学者 ID、详情、论文和合作关系的稳定性。

## 二、总体方向

优先由知识底座提供统一的姓名别名召回能力，ShenZhi 负责产品接口、权限边界、状态处理和结果适配。产品侧不自行猜测英文姓名，也不把机器翻译结果当作权威学者身份。

推荐调用链：

```text
用户输入姓名
→ ShenZhi Scholar Service 规范化 Query
→ Knowledge Integration 调用统一 Scholar Search
→ 知识底座按中文名/英文名/别名/author_id 召回
→ 返回稳定 scholar_id
→ ShenZhi 读取详情并展示论文、机构、合作学者
```

如果知识底座短期无法上线别名召回，采用受控的审核别名表作为临时过渡；过渡方案必须可追溯、可更新、可回滚，不能把通用翻译模型直接放入生产搜索链路。

## 三、范围与边界

### 本次范围

- Scholar Search 的中文名、英文名、姓名变体和 author_id 片段召回。
- Search 到 Detail 的稳定 ID 传递。
- 空结果、同名结果、上游不可用和详情不存在的状态处理。
- 搜索命中来源和改写信息的可观测性。

### 明确不做

- 不新增虚构 h-index、引用数、履历、邮箱或主页字段。
- 不在浏览器或 Next.js BFF 中直连知识底座。
- 不在 HTTP Integration Client 中写业务级姓名翻译逻辑。
- 不使用无来源机器翻译结果直接绑定学者实体。
- 不修改现有论文、图谱和 Funding 的实体契约。

## 四、分层设计

### 1. 前端层

继续使用现有 Scholar Client 和页面状态。前端只提交用户输入，展示结果、空结果和错误态；不维护姓名词典，不判断中文名对应哪个英文名。

### 2. ShenZhi Backend Service 层

新增独立的 Scholar Query 规范化和别名解析职责。该层负责：

- trim、空白归一化和长度校验；
- 识别是否为已审核别名；
- 记录原始 Query 与实际请求 Query；
- 对同名结果保持多结果返回，不擅自选择个人；
- 将上游错误映射为现有 Knowledge Error Contract。

### 3. Knowledge Integration 层

只负责调用上游接口、编码 opaque scholar_id、解析上游字段和转换异常。Integration 不保存产品别名规则，也不直接访问别名数据库。

### 4. 知识底座层

负责姓名索引、中文名与英文名别名、author_id 稳定性、同名排序和检索召回质量。长期正式方案应由此层提供。

## 五、分阶段实施

### 阶段 0：契约确认

由产品组和知识底座组先确认：

1. 中文名、英文名、姓名变体是否都进入同一个 Scholar Search。
2. 是否支持 author_id 片段查询。
3. 同名学者的返回排序和区分字段。
4. 别名来源、更新频率和错误修正流程。
5. 服务是否承诺空结果为 200，以及限流、超时和就绪状态。

阶段 0 未确认前，ShenZhi 不上线自动翻译兜底。

### 阶段 1：上游别名召回

知识底座增加别名查询能力，保持现有 Search/Detail 返回结构。ShenZhi 只需在 Service 和 Integration 层适配新增的可选命中元数据。

验收重点：同一学者的中文名和英文名返回相同 scholar_id；author_id 查询可以直接定位；同名结果不会被错误合并。

### 阶段 2：产品侧审核别名过渡

如果阶段 1 排期较晚，ShenZhi 增加审核别名表，仅收录已确认的高频学者。未命中别名表时仍使用原 Query，不返回猜测结果。

验收重点：别名命中可观测；别名错误可禁用；删除别名后立即恢复原始搜索；不影响英文搜索和其他实体。

### 阶段 3：灰度与回收

先对学者库页面灰度，再观察命中率、空结果率、详情一致率和错误率。上游别名能力稳定后，逐步减少产品侧临时别名，最终保留管理和审计能力，不保留重复的召回实现。

## 六、验收与回滚原则

必须同时满足：

- 中文名和英文名命中同一个稳定 scholar_id；
- Detail 的 id 必须与 Search 结果一致；
- 空结果仍是正常业务结果，不伪造卡片；
- 上游超时、限流和不可用状态不被转换为空结果；
- 任何 Query Rewrite 都能在日志中追踪原始值、改写值和规则来源，但不得记录敏感用户信息；
- 关闭 Rewrite 或别名表后，英文搜索和 author_id 搜索仍可用。

回滚只关闭别名解析或上游别名开关，不回滚 Scholar Search/Detail 基础契约。

## 七、具体接口与字段定义

### 7.1 当前 ShenZhi 接口

```text
GET /api/v1/knowledge/scholars/search?q={query}&limit=20&offset=0
GET /api/v1/knowledge/scholars/{scholarId}
```

上游对应：

```text
GET http://47.110.47.12/api/retrieval/scholars/search?q={query}&limit=20&offset=0
GET http://47.110.47.12/api/retrieval/scholars/{scholar_id}
```

### 7.2 建议的 Search 响应扩展

当前基础结构保持不变：

```json
{
  "results": [
    {
      "scholar_id": "author:...",
      "name": "Kaiming He",
      "paper_count": 11
    }
  ],
  "query": "何恺明"
}
```

如需增加诊断信息，使用可选字段，不改变现有字段含义：

```json
{
  "query": "何恺明",
  "normalized_query": "何恺明",
  "matched_by": "alias",
  "results": []
}
```

`matched_by` 建议枚举：`exact`、`alias`、`author_id`、`fuzzy`。如果上游暂时不提供该字段，ShenZhi 不自行伪造为上游事实。

### 7.3 ShenZhi Domain 字段

```text
ScholarSummary.id          string，opaque，必填
ScholarSummary.name        string，必填
ScholarSummary.paperCount  integer，>= 0，必填
ScholarSummary.provenance  object，必填
```

详情中的可选数组：

```text
years         integer[]
conferences   string[]
topics        string[]
funding       string[]
institutions  string[]
coauthors     { id: string, name: string }[]
papers        { id: string, title: string, year: integer | null }[]
```

### 7.4 临时审核别名表

```text
normalized_name   string，唯一索引
canonical_query   string，必填
scholar_id        string，可选；填写后可直接走详情
source             string，必填，记录来源或审核人
status             active | disabled
created_at         datetime
updated_at         datetime
```

禁止字段：未经审核的自动翻译结果、无法追溯来源的姓名映射、把多个不同学者强行合并的人工覆盖字段。

### 7.5 错误码

继续使用现有错误契约：

```text
INVALID_ARGUMENT       Query 为空、长度非法或分页参数非法
NOT_FOUND              详情 ID 不存在
RATE_LIMITED           上游限流，可重试
UPSTREAM_UNAVAILABLE   上游不可用，可按 retryable 决定重试
TIMEOUT                上游超时，可重试
CONTRACT_VIOLATION     上游字段不符合契约，不重试
```

### 7.6 最小测试矩阵

```text
中文名 -> 英文名结果的 scholar_id 一致
英文名 -> 结果和详情可打开
author_id -> 可定位对应学者
不存在姓名 -> 200 + results=[]
同名姓名 -> 返回多个候选，不自动合并
上游超时 -> TIMEOUT，不降级为空结果
别名禁用 -> 回到原始 Query 行为
```
