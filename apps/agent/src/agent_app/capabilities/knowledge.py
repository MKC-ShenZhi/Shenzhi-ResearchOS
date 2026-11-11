"""Knowledge Tools backed by Backend-owned Knowledge services."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

from agent_app.errors import BusinessError
from agent_app.execution.tools import Tool, tool
from agent_app.integrations.backend.knowledge import BackendKnowledgeClient

ABSTRACT_CHARS = 300
MAX_SEARCH_LIMIT = 20


def knowledge_tools(client: BackendKnowledgeClient | None = None) -> list[Tool]:
    knowledge = client or BackendKnowledgeClient()

    class SearchArgs(BaseModel):
        query: str
        limit: int = 10
        year_from: int | None = None
        year_to: int | None = None
        venue: str | None = None
        keyword: str | None = None

    class PaperArgs(BaseModel):
        paper_id: str

    class GraphArgs(BaseModel):
        paper_id: str
        depth: int = 1

    def brief(result: dict[str, Any]) -> dict[str, Any]:
        abstract = result.get('abstract') or ''
        return {
            'paper_id': result.get('id'), 'title': result.get('title'),
            'abstract': abstract[:ABSTRACT_CHARS] + ('…' if len(abstract) > ABSTRACT_CHARS else ''),
            'authors': (result.get('authors') or [])[:8], 'year': result.get('year'),
            'venue': result.get('venue'), 'keywords': (result.get('keywords') or [])[:5],
        }

    @tool(name='paper_search',
          description='检索 CS/AI 论文知识库，可按年份、venue 和关键词过滤；换角度检索扩大覆盖。',
          params=SearchArgs, timeout_s=90.0)
    async def paper_search(args: SearchArgs) -> str:
        payload: dict[str, Any] = {
            'query': args.query, 'topK': max(1, min(args.limit, MAX_SEARCH_LIMIT)),
        }
        if args.year_from is not None:
            payload['yearFrom'] = args.year_from
        if args.year_to is not None:
            payload['yearTo'] = args.year_to
        if args.venue:
            payload['venue'] = [args.venue]
        if args.keyword:
            payload['keyword'] = [args.keyword]
        response = await knowledge.search(payload)
        results = [brief(item) for item in response.get('results', [])]
        output: dict[str, Any] = {
            'results': results,
            'sparse': len(results) < max(1, min(args.limit, MAX_SEARCH_LIMIT)),
        }
        serialized = json.dumps(output, ensure_ascii=False)
        while len(serialized) > 7500 and results:
            results.pop()
            output['omitted'] = output.get('omitted', 0) + 1
            serialized = json.dumps(output, ensure_ascii=False)
        return serialized

    @tool(name='paper_detail',
          description='按 paper_id 获取论文完整摘要、作者、DOI 和 PDF 地址。',
          params=PaperArgs, timeout_s=90.0)
    async def paper_detail(args: PaperArgs) -> str:
        try:
            detail = await knowledge.get_paper(args.paper_id)
        except Exception as exc:
            raise BusinessError(20004, f'知识库无 {args.paper_id} 的详情；可换关键词重查或搜索公开页面') from exc
        payload = brief(vars(detail))
        payload.update({key: getattr(detail, key, None) for key in
                        ('doi', 'pdf_url', 'citation_count', 'reference_count')})
        return json.dumps(payload, ensure_ascii=False)

    @tool(name='citation_graph',
          description='返回论文引用邻域与主题标签；若没有 CITES 边，改用 paper_search 追后续工作。',
          params=GraphArgs, timeout_s=90.0)
    async def citation_graph(args: GraphArgs) -> str:
        graph = await knowledge.get_graph(args.paper_id, depth=max(1, min(args.depth, 3)))
        nodes = graph.get('nodes') or []
        titles = {node.get('id'): node.get('label', '') for node in nodes}
        cites = [edge for edge in graph.get('edges', [])
                 if str(edge.get('relation', '')).upper() == 'CITES']
        payload = {
            'root_id': graph.get('rootId'), 'citations_available': bool(cites),
            'backward': [{'paper_id': edge.get('targetId'),
                          'title': titles.get(edge.get('targetId'), '')}
                         for edge in cites if edge.get('sourceId') == graph.get('rootId')][:20],
            'forward': [{'paper_id': edge.get('sourceId'),
                         'title': titles.get(edge.get('sourceId'), '')}
                        for edge in cites if edge.get('targetId') == graph.get('rootId')][:20],
            'topics': [node.get('label') for node in nodes
                       if str(node.get('kind', '')).lower() == 'topic'][:10],
        }
        if not cites:
            payload['note'] = '当前知识库不提供引用关系（CITES），请用 paper_search 查询后续与批评工作。'
        return json.dumps(payload, ensure_ascii=False)

    return [paper_search, paper_detail, citation_graph]
