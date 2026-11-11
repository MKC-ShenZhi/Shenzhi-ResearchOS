# 学者库 V2 真实数据接入与联调

基线：`feat/scholars-v2` / `e3801ca`，开始时工作区干净。实测时间：2026-10-20 至 2026-10-21（Asia/Tokyo；请求证据另存 UTC 时间）。未提交、推送或合并任何分支。

## 1. 当前可用范围

正式 V2 默认使用真实 Provider，闭环为：输入姓名 → 分页搜索 → 学者画像 → 平台关联论文 → 原有论文详情 / DOI / PDF 来源。复用 V2 卡片、头像、画像、简介、柱图和响应式布局。无关键词访问显示“搜索学者”，不会伪装成全量目录。缺简介、机构、引用、年度统计不生成补充内容。

新版与旧版没有直接替换关系。总览、混合检索和原有 KnowledgeClient 仍使用 retrieval Scholar 契约；V2 使用同一个 KnowledgeBaseClient / KnowledgeAdapter / KnowledgeService 中新增的产品方法，路由和缓存命名分开。没有新增数据库、依赖、外部科研服务直连或合作网络实现。

```text
ScholarDataProvider（默认真实，测试可注入 Mock）
  → BffKnowledgeClient（clients/knowledge）
  → 同源 /api/v1/knowledge/*（既有通用 Next BFF）
  → FastAPI Knowledge API → KnowledgeService
  → KnowledgeAdapter → KnowledgeBaseClient
  → 知识底座 /api/v1/scholars/*
```

| ShenZhi API | 上游 API | 说明 |
| --- | --- | --- |
| `GET /api/v1/knowledge/scholar-profiles/search?q=...&limit=20&offset=0` | `/api/v1/scholars/search` | `items/limit/offset/total/has_more`；上游不提供 total 时保持 null |
| `GET /api/v1/knowledge/scholar-profiles/{encodedId}` | `/api/v1/scholars/{encodedId}` | 独立产品画像 Schema；校验返回 ID 与请求一致 |
| `GET /api/v1/knowledge/scholar-profile-papers?scholarId=...&limit=20&offset=0` | `/api/v1/scholars/{encodedId}/papers` | 复用 PaperDetail 映射；query ID 避免原始 ID 以 `/papers` 结尾时与详情路由冲突 |

浏览器不含知识底座地址；仅 FastAPI 的 `KNOWLEDGE_BASE_API_URL` 配置上游。沿用 `KNOWLEDGE_BASE_TIMEOUT_SEC`（默认 30 秒）、现有安全错误分类和 BFF 身份边界。浏览器 transport 组合调用方取消信号与 30 秒超时；可重试错误最多自动重试一次，保留主动取消的 AbortError。生产不自动回退 Mock。

Mock Provider 保留独立 fixtures、分页和取消能力，仅测试 / 显式组件注入使用。V2 默认真实模式不受旧版 `NEXT_PUBLIC_KNOWLEDGE_SOURCE=mock` 影响；不在真实页面显示 Mock Demo 标签或虚构人物声明。

## 2. 真实 GET 实测

服务地址为任务提供的 `<KNOWLEDGE_BASE_API_URL>`。沙箱内首次连接失败；允许外部网络的终端请求成功。以下状态来自真实 HTTP 请求，没有使用浏览器展示代替接口检查。接口未要求额外鉴权；这仅说明本轮这些公开 GET 的观察结果。

完整响应节选与耗时：[真实 GET 证据](fixtures/scholars-v2-live-2026-10-20.json)。其中大数组仅保留前四条并记录原始条数，长摘要省略；不是前端 Mock fixtures。

| 请求 / 条件 | 实际结果 |
| --- | --- |
| 新版搜索 `q=Marcel&limit=2&offset=0` | 200，`items/limit/offset`；含 `openalex:A5000001524`、`openalex:A5000000482` |
| 新版搜索无 q / `q=` | 均 400，`{"message":"q is required"}` |
| `q=Marcel&limit=20&offset=0` 与 offset=20 | 均 200，各 20 条；两页 ID 无交集，页 2 首条 Marcel Geppert |
| `q=Marcel&limit=100&offset=0` | 200，61 条；这是该关键词的本次返回数，不是全库总数 |
| 随机不存在姓名 | 200，`items:[]`；空结果不是服务错误 |
| limit=-1 / offset=-1 | 400，`Invalid pagination` |
| OpenAlex 画像 `openalex:A5000001524` | 200，姓名 Marcela Degrangemtsac；机构/年度引用为 []，bio/头像为 null，paper_count=0、citation_count=0 |
| 另一 OpenAlex 画像 `openalex:A5000000482` | 200，同样缺机构/简介/年度引用；返回更新时间与 citation_meta |
| 上述第一位 OpenAlex 学者论文 | 200，`items:[],total:0,limit:2,offset:0` |
| Marcel Kockmann 画像 `author:legacy:706867c1cd3d524922b44f19` | 重试 200，paper_count=11、citation_count=null；bio=null，机构/年度统计=[] |
| Geoffrey Hinton 画像 `author:legacy:d1381dc0b07a0347ebb834d5` | 200，paper_count=7、citation_count=null，更新时间=null |
| Marcel Kockmann 论文 limit=2，offset=0 与 2 | 均 200，total=11，两页论文不同；存在完整论文字段及平台 paper_id |
| 不存在的 Scholar ID | 404，`{"message":"Scholar not found"}` |
| 关联论文的 `/api/kg/paper?paperId=paper:alam17b_interspeech_2017_isca:81a0a1497158` | 200，返回相同论文标题、DOI 与 PDF 地址；未使用数字数据库行 ID 作为论文路由 |
| 新版 `q=何恺明` | 200，仅返回“何 良华”，未召回 Kaiming He |
| 新版 `q=Kaiming He` | limit=20 的首屏未含精确姓名；limit=100 中存在 `author:legacy:a3a064dec606544f98491242` / Kaiming He |
| 旧版 `/api/retrieval/scholars/search` 无 q，limit=2，offset=0 / 2 | 均 200，返回不同旧论文库候选（Yang Liu / Min Zhang；Haizhou Li / Jie Zhou） |

旧版虽支持浏览，但只返回 retrieval Schema，无法由该响应确认覆盖新采集 OpenAlex 学者，也没有总数。它可以支持“旧论文库作者候选”，不能证明是完整 V2 目录。本轮选择搜索初始态，不以旧候选冒充约 2000 条采集数据的全量浏览；不混用两套缓存或强行补齐画像字段。

一轮并发探测中，`q=a`、部分 legacy 画像及论文请求在客户端 18 秒截止时超时；降低并发后论文成功，画像再次请求也成功。最终串行脚本的全部 13 项请求取得 HTTP 响应。此证据不能单独归因于上游应用、网络或数据；记录为持续观察项，不宣称接口不存在或已达到稳定性验收。自动化测试另覆盖 httpx 超时、连接失败、404、429、503、非 JSON 的安全映射。

## 3. 字段与 UI 规则

| 产品字段 | 页面行为 / 校验 |
| --- | --- |
| scholar_id | 视为 opaque string；链接只在边界编码一次；详情 ID 必须一致；含 slash/中文/问号/字面百分号与 `/papers` 后缀均有契约测试 |
| name_zh / name_en | 中文优先，保留英文副标题；两者缺失显示“姓名暂缺”，不从 ID 推导姓名 |
| avatar_path | 实测均 null；首字母头像，中文名可兜底；失败的同一图片不重复显示；只接受 https 或本地受限演示图片路径，不能把上游相对路径解释为 Web 图片 |
| affiliations | 仅显示明确提供的 institution/position；空时机构信息暂无数据；不把机构关系解释为当前任职 |
| bio_zh / bio_en | 沿用双语切换；均缺失时空态；不由主题生成履历 |
| metrics.paper_count | 标签为“平台关联论文”，不等同 OpenAlex works_count；实测 Kockmann 的 11 与成果 total=11 一致 |
| metrics.citation_count | 原样区分 null 与数值 0；本轮 OpenAlex API 返回 0，legacy API 返回 null，不推断原始采集记录是否应为 0 |
| annual_citations | 产品契约为 `{year,count}`；验证非负整数或 null；重复年份视为契约错误；最近五个有统计年份，排序展示，不补缺失年、不将 null 当 0、不推导总引用 |
| citation_meta | 显示 source / coverage / as_of；已实测 OpenAlex source=OpenAlex、coverage=OpenAlex author record and works、as_of=null |
| updated_at | 有效日期才显示；不把采集更新时间推断为更新频率 |
| papers.items[].paper_id | 经现有 PaperDetail Adapter 映射为 id，忽略数据库数值 id；title/authors/year/conference/doi/pdf_url 映射为现有卡片字段 |
| papers.items[].external | 仅明确 false 才允许平台详情导航；true 或缺省不生成内部详情链接；可用 DOI/PDF 来源单独展示；Mock 不生成真实成果导航 |

产品前端不解析原始 OpenAlex `display_name/works_count/works/counts_by_year`。实测没有拿到非空机构、简介或年度引用，也没有源 works_count/h-index/i10-index，因此只能确认已观察字段的产品标准化；不能宣布 OpenAlex 全字段标准化已经验证。原始记录只有 Work ID / DOI 的情况不由前端伪造 PaperDetail，未来不同成果契约应先在 Backend Adapter 中用新实测样本验证。

搜索每页 20 条，q/page 写入 URL；新搜索及清空归第一页，卡片 returnTo 携带完整搜索页，侧栏恢复白名单加入 page。没有 total 时只显示本页数；满页允许尝试下一页，最后可能出现一页空结果，可返回上一页，不宣称精确总页数。画像与成果请求独立发起，画像超时也保留成果区域；成果错误有独立重试，不覆盖画像。

## 4. 验证与运行

本轮使用临时本机 FastAPI 18081 与 Web 13000；发现已有 Next dev 后保留原进程，改用生产构建预览。FastAPI 关闭 lifespan 恢复任务，仅验证读取链路；使用现有 loopback BFF 模式，不更改任何 `.env` 文件、持久化认证配置或远程服务。真实主流程完成的请求在 BFF / Backend 日志为 200，可追踪 request ID；主动离页取消与故障注入另行区分。

运行配置：Backend 设置 `KNOWLEDGE_BASE_API_URL`，Web 设置 `BUSINESS_BACKEND_URL` 指向 ShenZhi FastAPI；正常部署双方配置匹配的 `BACKEND_BFF_SECRET`。已有示例配置已经覆盖本次所需变量，无新增配置项。

从仓库根目录复测上游（只读、不携带认证 Cookie）：

```bash
python3 tools/verify_scholar_profiles.py \
  --base-url "<KNOWLEDGE_BASE_API_URL>" \
  --output /tmp/scholars-live.json
```

脚本逐条请求，不批量抓取全部学者；保存状态、耗时和 JSON，供底座组复现。约 2000 条数据的全量可检索数、更新周期和采集完整性尚不可由这些接口确认。

### 自动化检查

在 `apps/web`：`corepack pnpm typecheck`、`corepack pnpm lint`、`corepack pnpm test`、`corepack pnpm build`。在 `apps/backend`：`UV_CACHE_DIR=/tmp/shenzhi-uv-cache uv run --no-sync python -m unittest discover -s tests`。临时 uv 缓存路径用于当前沙箱权限，不是项目新增工具约定。

测试最终结果及浏览器验收记录见第 7 节。数据库相关 skip 不表示数据库故障；本轮未通过 `--env-file .env` 为 unittest 注入 CHAT_DATABASE_URL，未执行持久化集成测试。

## 5. 知识底座接口需求

仅下列已复现的接口缺口进入需求；未验证的原始字段映射、数据去重和约 2000 条覆盖量不列为已确认故障。

### KB-S01 无关键词的产品学者浏览（P1）

- 问题：V2 不能展示覆盖产品学者的初始目录。
- 当前接口及行为：新版 search 必须有 q；旧 retrieval 可浏览，但契约/数据覆盖不同。
- 证据：`browse_missing`、`browse_empty`、`recheck_missing_query` 返回 400 / q is required；旧 browse 两页 200。
- 产品预期：无词进入时按稳定顺序分页浏览产品学者，包括新采集 OpenAlex 学者。
- 建议变更：允许新版 q 缺省/空时浏览，或提供同一产品 Schema 的列表接口；明确稳定排序。
- 影响范围：学者库初次访问、清空搜索、全量数据核对。
- 责任方：知识底座组；产品组当前已交付搜索初始态，不阻塞姓名检索流程。

### KB-S02 搜索总数与全库覆盖信息（P2）

- 问题：无法展示精确总页数，也无法核对约 2000 条采集学者的可检索覆盖。
- 当前接口及行为：新版 search 返回 items/limit/offset，没有 total；论文接口已有 total。
- 证据：`recheck_search` 与 `recheck_search_next` 各 20 条、没有 total；`marcel_all` 返回 61 条也无 total。
- 产品预期：区分当前查询匹配总量与全库去重学者数量。
- 建议变更：search 增加去重 total（或明确 has_more/cursor）；如需核对采集批次，提供独立 summary/覆盖统计及更新时间定义。
- 影响范围：分页提示、最后一页、采集数据验收。当前产品通过本页数与可能下一页解决基本分页。
- 责任方：知识底座组。

### KB-S03 中文别名召回（P1）

- 问题：已存在英文记录不能通过给定中文姓名召回。
- 当前接口及行为：q=何恺明 只返回何 良华；q=Kaiming He&limit=100 含 Kaiming He。
- 证据：`chinese`、`recheck_chinese` 与 `he_all`，目标 ID 为 `author:legacy:a3a064dec606544f98491242`。
- 产品预期：有可靠中文名/别名关系时，中英文姓名能召回同一 Scholar ID。
- 建议变更：底座补充可信别名索引或规范化姓名查询；不要由前端维护任意人名翻译表。
- 影响范围：中文姓名搜索覆盖。V2 保持用户输入原样，不沿用旧 retrieval 的单个姓名 alias，以免改变新版排序/召回而掩盖缺口。
- 责任方：知识底座组。

### KB-S04 完整姓名的检索排序（P2）

- 问题：完整英文姓名存在，但默认首屏没有返回精确姓名。
- 当前接口及行为：Kaiming He、limit=20 返回 He Wang、Liang He 等；limit=100 才能在结果内观察到 Kaiming He（本次第 79 条）。
- 证据：`recheck_english` 的 20 条与 `he_all` 中目标 ID 对照。
- 产品预期：完整姓名的精确匹配优先于仅命中姓氏片段的候选。
- 建议变更：先按可信姓名/别名精确匹配排序，再返回模糊匹配；明确分词和排序契约。
- 影响范围：姓名检索可发现性。产品不通过抓取全部候选再本地重排来绕过分页。
- 责任方：知识底座组。

## 6. 待验证事项（不是已确认接口故障）

- 原始 OpenAlex works_count 与平台关联数的具体差值：产品 API 未暴露源作品总数，未取得对应原始记录，不能量化。
- 非空 annual_citations 的真实结构、引用覆盖和是否包含未结束年份：当前取样均 []；映射代码与空值规则有契约测试，非空真实数据仍待样本。
- 非空机构和任职、简介、external=true 的完整作品卡片：当前样本不足；不假定真实丰富画像已经验收。
- OpenAlex Work 与平台论文的匹配覆盖：两个已测 OpenAlex 学者成果为 0，legacy 学者存在平台论文；不能推断全库未匹配或数据丢失。
- 更新频率、全库唯一人数、约 2000 条采集批次完整性：仅有单条 updated_at，不等于更新 SLA 或全库总量。
- 合作网络无真实契约：现有静态网络原型未改动，不作为真实合作关系展示。
- 瞬时请求超时原因尚未定位；持续观察连接/耗时，不能把单次重试成功视为稳定性保证。


## 7. 最终验收记录

### 自动化测试（与真实请求分开计数）

| 检查 | 最终结果 |
| --- | --- |
| Web typecheck | 通过 |
| Web lint | 0 errors；原有 use-chat-session / use-popover-placement 两条 Hook 依赖 warning |
| Web test | 338 / 338 通过，包含隔离 Mock、真实 BFF 传输夹具、运行时 Schema 校验、分页恢复、空值/0、取消/错误、动态年份和图片失败兜底 |
| Web build | 通过；生产编译、TypeScript、30 个静态页面生成完成；使用此构建验证浏览器 |
| Backend Scholar V2 + 旧实体专项 | 12 项新增产品学者测试 + 32 项旧实体测试纳入全量通过 |
| Backend 全量 unittest | 460 项运行：433 通过、27 跳过、0 失败；skip 是未注入 CHAT_DATABASE_URL 的持久化测试，不代表数据库故障 |
| Python 语法编译 / git diff --check | 通过 |

React 组件复核：使用仓库现有 TanStack Query 去重与取消，Profile/Papers 独立请求；成果区域在画像加载状态变化时保持挂载，避免取消后重复请求；切换学者时成果组件 key 重置页码；卡片与返回来源复用现有导航工具；保留 label、搜索 form、键盘提交、状态提示、分页 button disabled 和 CSS 响应式。没有新增重型 UI 或测试依赖。最终生产构建复测中，Kockmann 成果请求（request ID `f804c4a6-8d7f-4686-8faa-b65218701f2c`）与画像请求（`c2e66c2d-f8de-4c06-9fb4-046fa921a61e`）各一次返回 200，未再因画像加载状态切换重取成果。

### 真实上游与浏览器验收

| 边界 / 行为 | 结果与证据 |
| --- | --- |
| 终端 → 知识底座 | 新版搜索、画像、论文三个接口真实 200；无词 400、缺失 404、非法分页 400；固定页大小两页不同；见响应证据 JSON |
| 浏览器 → BFF → FastAPI → 上游 | 本地生产预览，经同源 /api/v1/knowledge/*，BFF 和 Backend 请求日志 200；未将公网知识底座地址写入浏览器代码 |
| 初始状态 / 清空 | 初次访问不发空 q 搜索；显示输入姓名提示；清空后回搜索初始态 |
| 英文搜索 / 分页 | Marcel 首屏 20 条；下一页 URL 为 q=Marcel&page=2，首条 Marcel Geppert |
| 中文搜索 / 键盘 | 通过搜索框 Enter 提交何恺明，真实展示何 良华；确认传输正常，也确认中文召回缺口存在 |
| 画像 / 论文 | Marcel Kockmann 11 篇；最终构建 Marcel Geppert 2 篇；姓名、空简介、空机构、空引用、头像 initials 均与真实响应一致 |
| 内部论文详情 | 点击 Kockmann 的首篇成果，原有 /papers/{paper_id} 正常显示标题、作者、年份、摘要、DOI；返回回到学者画像 |
| 外部来源 | 成果的 DOI/PDF 链接来自真实响应；样本 ISCA PDF 另做终端只读 GET，200 / application/pdf；未逐篇验证全部外部链接 |
| 返回列表恢复 | 从 Marcel Geppert 画像点击返回，恢复 q=Marcel&page=2、搜索输入 Marcel、第二页结果；侧栏恢复规则亦包含 page |
| 请求失败 / 重试 | 暂停本次临时服务后提交新查询，页面出现“学者数据加载失败”和重试；恢复服务后点击重试，真实返回该随机姓名的空结果，没有 Mock 回退 |
| 桌面 / 移动 | 设置视口 1280×900 与 375×812；实际文档宽分别 1265 / 360（扣除滚动条），scrollWidth 与 clientWidth 相等；列表与画像未发现横向溢出 |
| Console | 正常完成搜索、画像、论文详情时未捕获到 warning/error；故障注入产生的请求失败属于预期测试，不视为正常路径错误 |

截图：[桌面真实画像](screenshots/scholars-v2-desktop.png)、[移动端第二页恢复](screenshots/scholars-v2-mobile.png)。截图为本轮真实数据，不是设计稿。

浏览器验收没有替代 API 验证。头像图片加载失败、未来非空机构/简介/年度图表的映射，以及 external=true 成果的隐藏内部链接规则有自动化契约/逻辑覆盖，但没有对应真实上游样本的完整浏览器验收。成果 UI 的分页已经实现，真实论文 offset 已终端验证；浏览器所选样本最多 11 篇，没有验收超过 20 篇成果的下一页点击。未做真机软键盘、全面键盘焦点遍历或约 2000 条全库数据验收。

主流程已能使用当前可用真实数据。后续底座配合优先处理产品浏览与中文召回，再补总数、排序及丰富画像的真实样本；非空年度统计、源作品总数、更新频率与全量覆盖仍需底座证据，不标记为已通过。
