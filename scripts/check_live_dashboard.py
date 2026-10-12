"""Verify deployed files match this build; a green upload is not a sync check."""
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

FILES = ['data/rrg-core.json', 'data/rrg-audit.json', 'data/sector-breadth.json',
         'rrg.html', 'sector-breadth.html', 'breadth-feed.js', 'breadth-confirmation.js']


def verify(base):
    local = {name: Path(name).read_bytes() for name in FILES}
    breadth = json.loads(local['data/sector-breadth.json'])
    if breadth.get('status') != 'ok' or len(breadth.get('rows', [])) != 11:
        raise RuntimeError('Equal-weight build is unavailable or incomplete; live sync cannot pass')
    def check(name):
        try:
            r = requests.get(base.rstrip('/') + '/' + name, params={'verify': hashlib.sha256(local[name]).hexdigest()[:16]},
                             timeout=15, headers={'Cache-Control': 'no-cache'})
            if r.status_code != 200:
                return f'{name}: HTTP {r.status_code}'
            if hashlib.sha256(r.content).digest() != hashlib.sha256(local[name]).digest():
                return f'{name}: deployed content differs from this build'
            return None
        except requests.RequestException as exc:
            return f'{name}: {type(exc).__name__}'
    with ThreadPoolExecutor(max_workers=6) as pool:
        failures = [e for e in pool.map(check, FILES) if e]
    if failures:
        raise RuntimeError('; '.join(failures))
    print(f'Live sync verified: {len(FILES)} exact files, 11/11 pairs, session {breadth["as_of"]}')


if __name__ == '__main__':
    for attempt in range(4):
        try:
            verify(sys.argv[1])
            break
        except (RuntimeError, OSError, ValueError) as exc:
            print(f'Live verification attempt {attempt + 1}/4: {exc}', flush=True)
            if attempt == 3:
                raise SystemExit(1)
            time.sleep(5)
