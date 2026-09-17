# 知识库端点经验（2026-09 实测）

条目按 academic-search 的出处纪律组织；`实测` 标记的都经过真实请求验证。过时了就改，不要供奉。

## /api/retrieval/search（paper_search）

- `top_k` 客户端上限 **100**（2026-09 复测：服务端本就支持 100+，旧笔记的 20 是客户端自我截断，已释放）。
- 检索行**没有 pdf_url**——全文链接要走 `paper_detail`。有 `conference` 字段（会议名）。
- 无引用数字段；"高被引"判断只能靠 venue 与领域常识。
- 空结果是真查无；HTTP 错误/超时是渠道故障（返回 `knowledgeBaseError`），二者含义完全不同。

## /api/retrieval/multistep-search

- 适合"作者×主题""引用×年份"这类复合约束；普通关键词查询用它没有增益。
- `max_steps` 上限 6。返回 `queryParse`（服务端的查询理解），可据此发现约束理解偏差。

## /api/kg/paper（paper_detail）

- id 必须带 `paper:` 前缀（服务端 `canonicalPaperId` 已兜底补全，模型丢前缀也能查到）。
- 404 = 知识库里没有这篇（不代表论文不存在）；错误信息会带 paperId 便于定位。
- 返回字段：paper_id / title / authors / year / venue / abstract / doi / **pdf_url**——pdf_url 是全文阅读的主要入口。

## /api/kg/graph（citation_graph）

- **混合知识图谱，不是引文索引**。实测一篇论文的邻域：HAS_TOPIC 22、AUTHORED_BY 13、PUBLISHED_IN 2、CITES 仅 1。CITES 边稀少。
- **结构化分组**（2026-09 起）：返回已按 backward/forward/topics/authors 分组，方向语义 from→to = from 引用 to；不用自己从混合边表里数。
- **CITES 密度因种子而异**：RAG 类论文 depth=1 仅 1 条 CITES；BERT 类种子可返回 81 条 CITES（几乎全为 forward，backward 常为 0——被引多的大种子，backward 递追收益低，forward 才是主产出面）。换几个种子展开再判断。
- **检索行 subjects/keywords 实测基本为空**（100 行抽样 subjects 0/100、keywords 5/100；detail 行无此字段）——聚组请用 citation_graph 的 topics，别依赖检索行标签。
- 用途按边型分：CITES 找奠基/后续/批评性工作；HAS_TOPIC 找同主题论文；AUTHORED_BY 找作者脉络。找引文邻域时不要指望一次展开就够——换几篇种子论文多展开。
- 节点带完整元数据（含 pdf_url），可引用。
- depth 参数实际对返回规模影响不大（实测 depth=1 与 2 返回相同）；别为省成本纠结 depth。

## 检索语料特征

- 语料以英文 CS/AI 为主（arXiv 系 id 形如 `paper:2605.06716v1`）：中文问题先译成英文检索词。
- 快照随知识库更新（数据集标记 PAPER_DATA_20260528）；时间敏感的问题注意语料截止点，需要更新的信息走 web_search。
