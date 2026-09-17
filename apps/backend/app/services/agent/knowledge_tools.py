"""知识库检索工具：论文检索、详情、引用邻域。

三个工具都是**基座级**的（与 read_paper / fetch_url 同层），不是某个技能私有的：
技能正文只写"怎么查"（手艺），能查什么由基座提供——技能删了工具还在，技能来了直接用。

调用链固定走既有边界：tools → KnowledgeService → integrations/knowledge → 上游。
失败降级：上游不可用 → 工具抛错 → registry 统一转 is_error 回喂模型
（模型向用户说明渠道受限，不伪造文献）。

两条与实测对齐的纪律（见 docs/agent/agent-base-cleanup-plan.md）：

1. **能力声明必须与数据一致**：上游图谱只有 HAS_TOPIC / AUTHORED_BY / PUBLISHED_IN /
   PART_OF，**没有 CITES**。`citation_graph` 因此显式返回 `citations_available`，而不是
   交回一个含义不明的空邻域——模型看到空数组只会反复重试，看到"该渠道不提供引用关系"
   才知道该换检索追后续工作。
2. **错误文案必须是下一步动作**：失败要带可执行的补救路径（换措辞重查 / 查公开页面）。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, TypeVar

from pydantic import BaseModel

from app.core.errors import BusinessError
from app.integrations.knowledge.exceptions import KnowledgeIntegrationError
from app.services.agent.tools import Tool, ToolOutput, tool
from app.services.knowledge import KnowledgeService, KnowledgeServiceError
from app.services.knowledge_query import normalize_knowledge_query
from app.schemas.knowledge import KnowledgeSearchRequest

ABSTRACT_CHARS = 800
TRANSIENT_RETRIES = 1        # 实测上游约 15% 的 graph 请求瞬时断连；重试一次即可消除
TRANSIENT_RETRY_DELAY_S = 0.5
MAX_SEARCH_LIMIT = 100       # 上游 top_k 实测 100 仍正常返回（曾误砍到 30，等于自断覆盖面）

T = TypeVar('T')


async def _call_with_transient_retry(operation: Callable[[], Awaitable[T]]) -> T:
    """瞬时渠道失败重试一次；不可重试错误（契约违规 / 404 类）原样抛出。"""
    attempt = 0
    while True:
        try:
            return await operation()
        except KnowledgeIntegrationError as exc:
            if not exc.retryable or attempt >= TRANSIENT_RETRIES:
                raise
        except KnowledgeServiceError as exc:
            error = getattr(exc, 'error', None)
            if error is None or not getattr(error, 'retryable', False) \
                    or attempt >= TRANSIENT_RETRIES:
                raise
        except (TimeoutError, OSError):
            if attempt >= TRANSIENT_RETRIES:
                raise
        attempt += 1
        await asyncio.sleep(TRANSIENT_RETRY_DELAY_S * attempt)


def _brief(result: Any, *, source: str) -> dict:
    abstract = result.abstract or ''
    authors = list(result.authors or [])
    brief = {
        'paper_id': result.id,
        'title': result.title,
        'abstract': abstract[:ABSTRACT_CHARS] + ('…' if len(abstract) > ABSTRACT_CHARS else ''),
        'authors': authors[:8],
        'year': result.year,
        'venue': result.venue,
        'keywords': list(result.keywords or [])[:8],
    }
    # 检索接口不返回作者（实测恒为 []），详情接口才返回：需要作者时必须知道"去调 detail"
    if not authors and source == 'search':
        brief['authors_note'] = '检索接口不返回作者；需要作者请对该 paper_id 调用 paper_detail。'
    return brief


def knowledge_tools(service: KnowledgeService | None = None) -> list[Tool]:
    """工厂：返回知识库三件套（paper_search / paper_detail / citation_graph）。"""
    knowledge = service or KnowledgeService()

    class SearchArgs(BaseModel):
        query: str
        limit: int = 10
        # 上游支持的过滤（实测有效）：年份区间、venue、关键词能显著改变结果集，
        # 是"按槽覆盖"而不是反复改措辞撞运气的手段。（author/subject 上游未生效，故不暴露。）
        year_from: int | None = None
        year_to: int | None = None
        venue: str | None = None
        keyword: str | None = None

    class PaperArgs(BaseModel):
        paper_id: str

    class GraphArgs(BaseModel):
        paper_id: str
        depth: int = 1

    @tool(name='paper_search',
          description='检索 CS/AI 论文知识库（混合检索：精确 + 模糊 + 语义）。可按年份区间、'
                      'venue、关键词过滤。返回 paper_id、标题、摘要、年份、venue。'
                      '换措辞重查往往能拿到完全不同的论文——这是扩大覆盖的主要手段。',
          params=SearchArgs, timeout_s=90.0)
    async def paper_search(args: SearchArgs) -> str:
        query = normalize_knowledge_query(args.query)
        payload: dict = {'query': query, 'topK': max(1, min(args.limit, MAX_SEARCH_LIMIT))}
        if args.year_from is not None:
            payload['yearFrom'] = args.year_from
        if args.year_to is not None:
            payload['yearTo'] = args.year_to
        if args.venue:
            payload['venue'] = args.venue
        if args.keyword:
            payload['keyword'] = args.keyword
        response = await _call_with_transient_retry(
            lambda: knowledge.search(KnowledgeSearchRequest.model_validate(payload)))
        results = [_brief(item, source='search') for item in response.results]
        return json.dumps({'results': results, 'sparse': len(results) < args.limit},
                          ensure_ascii=False)

    @tool(name='paper_detail',
          description='按 paper_id 获取论文详情（完整摘要、作者、DOI、pdf_url）。',
          params=PaperArgs, timeout_s=90.0)
    async def paper_detail(args: PaperArgs) -> str:
        try:
            detail = await _call_with_transient_retry(
                lambda: knowledge.get_paper(args.paper_id))
        except Exception as exc:  # noqa: BLE001 — 统一转成带补救路径的错误
            raise BusinessError(
                20004,
                f'知识库无 {args.paper_id} 的详情（{exc}）。下一步任选：'
                f'① paper_search 用标题关键词换措辞重查；'
                f'② web_search 搜"该论文标题 + arXiv"获取公开页面信息。'
            ) from exc
        payload = _brief(detail, source='detail')
        payload.update({'doi': detail.doi, 'pdf_url': detail.pdf_url,
                        'citation_count': detail.citation_count,
                        'reference_count': detail.reference_count})
        return json.dumps(payload, ensure_ascii=False)

    @tool(name='citation_graph',
          description='按 paper_id 返回引用邻域与主题标签。citations_available=false 表示'
                      '当前知识库不提供引用关系，此时改用 paper_search 追后续与批评工作，'
                      '不要反复重试本工具。',
          params=GraphArgs, timeout_s=90.0)
    async def citation_graph(args: GraphArgs) -> str:
        try:
            graph = await _call_with_transient_retry(
                lambda: knowledge.get_graph(args.paper_id, depth=max(1, min(args.depth, 3))))
        except Exception as exc:  # noqa: BLE001
            raise BusinessError(
                20004,
                f'知识库无 {args.paper_id} 的引文图（{exc}）。'
                f'可跳过追溯，改用 paper_search 检索该文的后续与批评工作。'
            ) from exc
        titles = {node.id: node.label for node in graph.nodes}
        cites = [edge for edge in graph.edges if edge.relation.upper() == 'CITES']
        backward = [{'paper_id': edge.target_id, 'title': titles.get(edge.target_id, '')}
                    for edge in cites if edge.source_id == graph.root_id]   # root 引的：奠基/前置
        forward = [{'paper_id': edge.source_id, 'title': titles.get(edge.source_id, '')}
                   for edge in cites if edge.target_id == graph.root_id]    # 引 root 的：后续/批评
        topics = [node.label for node in graph.nodes if node.kind.lower() == 'topic']
        payload: dict = {
            'root_id': graph.root_id,
            'citations_available': bool(cites),
            'backward': backward[:20],
            'forward': forward[:20],
            'topics': topics[:10],
        }
        if not cites:
            # 有能力无数据 ≠ 查询有误：把事实与下一步一起交出去，避免模型在空结果上打转。
            payload['note'] = ('该知识库当前不提供引用关系（CITES）：backward/forward 必然为空，'
                               '这不是查询错误，重试无意义。改用 paper_search 检索该文的后续、'
                               '批评与应用工作；topics 可用于改写检索词。')
            return ToolOutput(content=json.dumps(payload, ensure_ascii=False),
                              unavailable=('citations',))
        return json.dumps(payload, ensure_ascii=False)

    return [paper_search, paper_detail, citation_graph]
