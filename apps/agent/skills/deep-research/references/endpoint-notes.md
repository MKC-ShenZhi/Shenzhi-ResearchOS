# 研究工具使用经验

本文件保留来源分支中有用的查询与降级经验。Skill 只依赖 Agent Tool 的输入输出语义；知识库连接由 `KnowledgeService` 处理。工具结果中的错误、空列表和截断标记应分别判断。

## `paper_search`

- 输入 `query`；可给 `limit`（最高 100）、`year_from` / `year_to`、`venue`、`keyword`。没有复合查询专用 Tool；作者×主题等问题用多轮查询、过滤和详情交叉核对。
- 返回 `results` 与 `sparse`。`sparse: true` 只表示本次返回数少于请求数，不证明领域无论文。改写术语、缩写、语言或任务词后仍无新线索，才把该渠道记为覆盖不足。
- 检索行给 `paper_id`、标题、截断摘要、年份、venue、关键词；作者常为空且有 `authors_note`。不要把空作者当作匿名论文，也不要把摘要当全文。
- 检索行通常没有 PDF URL；需要作者、完整摘要、DOI 或 PDF URL 时调用 `paper_detail`。查询错误、超时与零结果分开记录。

## `paper_detail`

- 输入工具返回的 `paper_id`，用于核对标题、完整摘要、作者、年份、venue、DOI、PDF URL，以及可用时的引用/参考文献计数。详情缺失只说明此知识库没有该条详情，不证明论文不存在。
- `pdf_url` 可供 `read_paper` 使用；没有 PDF URL 时可用论文公开页面或 DOI 线索经 `web_search` 查找，再用 `read_paper` / `fetch_url` 核对。
- 引用计数若存在，只保留这个平台的口径；不跨来源求和，也不把计数当作质量或相关性的替代。

## `citation_graph`

- 输入 `paper_id`，可给 `depth`（工具限制为 1–3）。返回 `root_id`、`citations_available`、`backward`（该文引用的论文）、`forward`（引用该文的论文）和 `topics`。
- 图谱可能以主题关系为主，CITES 边稀少。`citations_available: false` 表示这次结果没有 CITES 边；不要对同一论文反复重试。改用 `paper_search` 找后续、批评与相关主题，必要时换其他代表性种子。`topics` 可帮助改写查询。
- 邻域条目只有简要标识与标题时，不足以支撑论文细节；先用 `paper_detail` 或 `read_paper` 核对。

## 全文与公开网络

- `read_paper` 接受 `paper_id` 或 `url`；PDF 返回 `pdf: true`、带 `--- p.N ---` 的文本和页数/截断信息。可用 `page_from`、`page_to` 续读；`pdf: false` 是网页正文，按页面级证据处理。
- `web_search` 返回标题、URL、摘要；摘要用于找线索。承重的当前事实优先用 `fetch_url` 读取原网页正文，记录最终 URL、日期与来源身份（若返回）。
- 某渠道不可用时记为渠道受限。不要把网络故障、工具错误或知识库语料时效误写成领域空白。
