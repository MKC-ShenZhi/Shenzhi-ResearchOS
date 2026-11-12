"""Development source serving the proposed upstream NSFC project API."""

from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

snapshot_api = FastAPI(title='NSFC snapshot', docs_url=None, openapi_url=None)
SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / 'data' / 'nsfc-projects.jsonl'


@lru_cache(maxsize=1)
def catalog():
    records = {}
    with SNAPSHOT_PATH.open(encoding='utf-8') as file:
        for line in file:
            record = json.loads(line)
            project = next(
                node['properties'] for node in record['graph']['nodes'] if node['label'] == 'Project'
            )
            records[project['award_number']] = (project, record)

    source_counts = Counter(project['source_url'] for project, _ in records.values())
    for project, _ in records.values():
        if source_counts[project['source_url']] > 1:
            project['source_url'] = ''

    return dict(sorted(
        records.items(), key=lambda pair: (pair[1][0]['award_year'], pair[0]), reverse=True
    ))


@snapshot_api.get('/api/retrieval/nsfc-projects')
def search_projects(
    q: Annotated[str, Query(max_length=200)] = '',
    keyword: Annotated[str, Query(max_length=200)] = '',
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    terms = q.casefold().split()
    exact_keyword = keyword.strip().casefold()
    results = []
    for project, _ in catalog().values():
        if exact_keyword and not any(
            topic.strip().casefold() == exact_keyword for topic in project['research_topics']
        ):
            continue
        text = ' '.join([
            project['award_number'], project['name'], project['summary'],
            *project['research_topics'],
            *(member['name'] for member in project['principal_investigators']),
            *(institution['name'] for institution in project['host_institutions']),
        ]).casefold()
        if all(term in text for term in terms):
            results.append(project)

    return {'items': results[offset:offset + limit], 'total': len(results)}


@snapshot_api.get('/api/retrieval/nsfc-projects/{award_number}')
def get_project(award_number: str):
    item = catalog().get(award_number.upper())
    if item is None:
        raise HTTPException(status_code=404)
    return item[1]
