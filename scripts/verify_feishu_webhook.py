#!/usr/bin/env python3
"""Send one signed Feishu message to verify a test group's webhook."""

import argparse
import base64
from datetime import datetime, timezone
import hmac
from http.client import HTTPException
import json
import os
import re
import sys
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


WEBHOOK_URL = re.compile(r'https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9_-]+')


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def label(value: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', value):
        raise argparse.ArgumentTypeError('Use 1-64 letters, digits, dots, underscores or hyphens.')
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', type=label, default='monitoring', help='Source service label')
    parser.add_argument('--component', type=label, help='Source component label, such as worker or agent-gateway')
    parser.add_argument('--environment', type=label, default='test', help='Source environment label')
    args = parser.parse_args(argv)

    webhook_url = os.environ.get('FEISHU_WEBHOOK_URL', '').strip()
    secret = os.environ.get('FEISHU_WEBHOOK_SECRET', '').strip()
    if not webhook_url or not secret:
        print('Set FEISHU_WEBHOOK_URL and FEISHU_WEBHOOK_SECRET for the test group.', file=sys.stderr)
        return 2
    if not WEBHOOK_URL.fullmatch(webhook_url):
        print('FEISHU_WEBHOOK_URL must be a Feishu v2 custom bot HTTPS webhook.', file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    timestamp = str(int(now.timestamp()))
    signing_key = f'{timestamp}\n{secret}'.encode('utf-8')
    signature = base64.b64encode(hmac.digest(signing_key, b'', 'sha256')).decode('ascii')
    test_id = uuid4().hex
    source = f'{args.service}/{args.component}' if args.component else args.service
    payload = {
        'timestamp': timestamp,
        'sign': signature,
        'msg_type': 'text',
        'content': {
            'text': f'[TEST] ShenZhi 告警 Bot 通信验证\n'
                    f'Environment: {args.environment}\n'
                    f'Source: {source}\n'
                    f'Test ID: {test_id}\n'
                    f'UTC: {now.isoformat(timespec="seconds")}',
        },
    }
    request = Request(
        webhook_url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    print(f'Test ID: {test_id}', flush=True)
    try:
        with build_opener(NoRedirects()).open(request, timeout=10) as response:
            result = json.loads(response.read(16_384))
    except HTTPError as error:
        print(f'Feishu request failed (HTTP {error.code}).', file=sys.stderr)
        return 1
    except (OSError, HTTPException):
        print('Feishu request failed. Check HTTPS connectivity and timeout.', file=sys.stderr)
        return 1
    except ValueError:
        print('Feishu returned an invalid JSON response.', file=sys.stderr)
        return 1

    code = result.get('code') if isinstance(result, dict) else None
    if type(code) is not int:
        print('Feishu response did not contain a numeric business code.', file=sys.stderr)
        return 1
    if code != 0:
        print(f'Feishu rejected the request (code {code}).', file=sys.stderr)
        return 1

    print('Feishu accepted the request. Verify the matching Test ID in the test group.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
