"""HTTP client and adapter for the two NSFC project endpoints."""

import os
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from pydantic import ValidationError

from app.integrations.knowledge.client import KnowledgeBaseClient
from app.integrations.knowledge.exceptions import KnowledgeIntegrationError
from app.integrations.knowledge.nsfc_snapshot import snapshot_api
from app.schemas.nsfc_project import ProjectDetail, ProjectList, ProjectSummary

PROJECTS_PATH = '/api/retrieval/nsfc-projects'


def _https_url(value: str | None) -> str | None:
    if not value or any(character.isspace() or ord(character) < 32 for character in value):
        return None
    try:
        url = urlsplit(value)
        if url.scheme == 'https' and url.hostname and not url.username and not url.password:
            return value
    except ValueError:
        pass
    return None


def _summary(project: dict[str, Any]) -> ProjectSummary:
    output_papers = project.get('output_papers')
    return ProjectSummary(
        award_number=project['award_number'],
        name=project['name'],
        award_year=project['award_year'],
        status=project['project_status'],
        program=(project.get('program_id') or '').removeprefix('program:'),
        institutions=[item['name'] for item in project['host_institutions']],
        topics=project.get('research_topics') or [],
        summary=project.get('summary') or '',
        principal_investigators=[
            member['name'] for member in (project.get('principal_investigators') or [])
            if member['role'] == 'PI'
        ],
        paper_count=len(set(output_papers)) if isinstance(output_papers, list) else None,
    )


class NsfcProjectsAdapter(KnowledgeBaseClient):
    def __init__(self):
        base_url = os.getenv('NSFC_PROJECTS_API_URL', '').strip()
        self.snapshot = not base_url
        transport = httpx.ASGITransport(app=snapshot_api, raise_app_exceptions=False) if self.snapshot else None
        super().__init__(base_url=base_url or 'http://nsfc-snapshot', transport=transport)

    async def search_projects(self, q: str, limit: int, offset: int, *, keyword: str = '') -> ProjectList:
        params = {'q': q, 'limit': limit, 'offset': offset}
        if keyword:
            params['keyword'] = keyword
        body = await self._request_json(
            'GET', PROJECTS_PATH, params=params,
            validate=lambda value: isinstance(value.get('items'), list),
        )
        try:
            return ProjectList(
                items=[_summary(item) for item in body['items']],
                total=body['total'],
                snapshot=self.snapshot,
            )
        except (KeyError, TypeError, AttributeError, ValidationError) as error:
            raise KnowledgeIntegrationError.contract_violation() from error

    async def get_project(self, award_number: str) -> ProjectDetail:
        body = await self._request_json('GET', f'{PROJECTS_PATH}/{quote(award_number, safe="")}')
        try:
            graph = body['graph']
            nodes = {node['id']: node for node in graph['nodes']}
            project_id = f'project:{award_number}'
            node = nodes[project_id]
            project = node['properties']
            if node['label'] != 'Project' or project['award_number'] != award_number:
                raise KnowledgeIntegrationError.contract_violation()

            paper_ids = dict.fromkeys(
                edge['target'] for edge in graph['edges']
                if edge['type'] == 'PRODUCES_PAPER' and edge['source'] == project_id
            )
            papers = []
            for paper_id in paper_ids:
                paper = nodes[paper_id]
                if paper['label'] != 'Paper':
                    raise KnowledgeIntegrationError.contract_violation()
                papers.append({
                    'id': paper_id,
                    'title': paper['properties']['title'],
                    'source_url': _https_url(paper['properties'].get('source_url')),
                })

            summary = _summary(project).model_dump()
            summary['paper_count'] = len(papers)
            return ProjectDetail(
                **summary,
                start_date=project.get('start_date') or '',
                end_date=project.get('end_date') or '',
                source_url=_https_url(project.get('source_url')),
                members=[
                    {'name': member['name'], 'role': member['role']}
                    for member in project['principal_investigators']
                ],
                papers=papers,
                snapshot=self.snapshot,
            )
        except (KeyError, TypeError, AttributeError, ValidationError) as error:
            raise KnowledgeIntegrationError.contract_violation() from error
