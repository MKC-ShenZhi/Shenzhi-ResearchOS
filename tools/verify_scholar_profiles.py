#!/usr/bin/env python3
"""Read-only live probes. No fixture fallback, credentials, or browser dependency.

python3 tools/verify_scholar_profiles.py --base-url http://host:port --output /tmp/scholars.json
Each request is sequential to avoid overloading the research service.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import urlopen


def probe(base_url: str, path: str, timeout: float) -> dict:
    started = time.monotonic()
    try:
        try:
            response = urlopen(base_url + path, timeout=timeout)
        except HTTPError as error:
            response = error
        with response:
            content = response.read().decode('utf-8')
            try:
                body = json.loads(content)
            except ValueError:
                body = {'non_json': True, 'content_type': response.headers.get('Content-Type')}
            return {'path': path, 'status': response.status,
                    'seconds': round(time.monotonic() - started, 3), 'body': body}
    except (URLError, TimeoutError, OSError) as error:
        # No exception string: it may include deployment-specific connection details.
        return {'path': path, 'error_type': type(error).__name__,
                'seconds': round(time.monotonic() - started, 3)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default=os.getenv('KNOWLEDGE_BASE_API_URL', ''))
    parser.add_argument('--query', default='Marcel')
    parser.add_argument('--scholar-id', default='author:legacy:706867c1cd3d524922b44f19')
    parser.add_argument('--timeout', type=float, default=20)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error('Provide an HTTP(S) base URL without credentials or query parameters')
    if args.timeout <= 0 or args.timeout > 60:
        parser.error('timeout must be in (0, 60]')
    paths = {
        'missing_query': '/api/v1/scholars/search?limit=2&offset=0',
        'empty_query': '/api/v1/scholars/search?q=&limit=2&offset=0',
        'search': '/api/v1/scholars/search?' + urlencode({'q': args.query, 'limit': 20, 'offset': 0}),
        'search_next': '/api/v1/scholars/search?' + urlencode({'q': args.query, 'limit': 20, 'offset': 20}),
        'chinese': '/api/v1/scholars/search?' + urlencode({'q': '何恺明', 'limit': 20, 'offset': 0}),
        'english': '/api/v1/scholars/search?' + urlencode({'q': 'Kaiming He', 'limit': 20, 'offset': 0}),
        'no_matches': '/api/v1/scholars/search?q=zzzzScholarsNoSuchPerson987&limit=2&offset=0',
        'invalid_pagination': '/api/v1/scholars/search?q=Marcel&limit=-1&offset=-1',
        'profile': '/api/v1/scholars/' + quote(args.scholar_id, safe=''),
        'papers': '/api/v1/scholars/' + quote(args.scholar_id, safe='') + '/papers?limit=2&offset=0',
        'papers_next': '/api/v1/scholars/' + quote(args.scholar_id, safe='') + '/papers?limit=2&offset=2',
        'missing_profile': '/api/v1/scholars/openalex%3ANOTEXIST',
        'legacy_browse': '/api/retrieval/scholars/search?limit=2&offset=0',
    }
    results = {}
    for name, path in paths.items():
        results[name] = probe(args.base_url.rstrip('/'), path, args.timeout)
        print(name, results[name].get('status', results[name].get('error_type')), flush=True)
    report = {'observed_at': datetime.now(timezone.utc).isoformat(), 'results': results}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
