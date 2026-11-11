"""Agent Tool adapter for the shared web-search integration."""
from __future__ import annotations

import json

from pydantic import BaseModel

from agent_app.errors import BusinessError
from agent_app.integrations.web_search.provider import web_search
from agent_app.execution.tools import Tool, tool


class WebSearchArgs(BaseModel):
    query: str


def web_search_tool() -> Tool:
    """Expose the shared search provider as the Agent's ``web_search`` tool."""

    @tool(name='web_search',
          description='联网搜索实时信息（新闻、文档、近期进展、时间敏感事实）。返回标题、URL 与摘要列表；'
                      '学术文献优先用知识库技能。',
          params=WebSearchArgs, timeout_s=90)
    async def search(args: WebSearchArgs) -> str:
        items, warnings = await web_search(args.query)
        if not items:
            raise BusinessError(20004, '；'.join(warnings) or '联网搜索未获得结果')
        return json.dumps([{'title': item['title'], 'url': item['url'],
                            'snippet': item['snippet']} for item in items], ensure_ascii=False)

    return search
