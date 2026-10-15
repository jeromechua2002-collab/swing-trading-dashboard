"""Verify deployed files match this build; a green upload is not a sync check."""
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

STOCK_SECTORS = ("XLK", "XLY", "XLC", "XLF", "XLI", "XLB", "XLV", "XLE", "XLP", "XLU", "XLRE")
FILES = [
    'index.html', 'desk-home.css', 'desk-health.js', 'data/release-manifest.json',
    'data/journal-performance.json', 'equity.html', 'calendar.html',
    'data/rrg-core.json', 'data/rrg-audit.json', 'data/sector-breadth.json',
    'rrg.html', 'data/rrg-reference-trajectory-audit.json', 'sector-breadth.html', 'breadth-feed.js', 'breadth-confirmation.js',
    'stock-leadership.html', 'stock-leadership.js', 'trade-gate.html', 'trade-gate.js',
    *(f'data/stocks/{sector}.json' for sector in STOCK_SECTORS),
]


def verify(base):
    local = {name: Path(name).read_bytes() for name in FILES}
    breadth = json.loads(local['data/sector-breadth.json'])
    if breadth.get('status') != 'ok' or len(breadth.get('rows', [])) != 11:
        raise RuntimeError('Equal-weight build is unavailable or incomplete; live sync cannot pass')
    manifest = json.loads(local['data/release-manifest.json'])
    if manifest.get('market_status') != 'validated_completed_session':
        raise RuntimeError('The published release is not a validated completed-session snapshot')
    if manifest.get('breadth_session') != breadth.get('as_of'):
        raise RuntimeError('Release manifest/breadth session mismatch')
    for key, path in (
        ('rrg', 'data/rrg-core.json'),
        ('breadth', 'data/sector-breadth.json'),
        ('journal', 'data/journal-performance.json'),
    ):
        if manifest['sha256'].get(key) != hashlib.sha256(local[path]).hexdigest():
            raise RuntimeError(f'Release manifest hash mismatch: {key}')
    if len(STOCK_SECTORS) != 11:
        raise RuntimeError('Expected all 11 sector stock JSON files')
    xlv = json.loads(local['data/stocks/XLV.json'])
    if xlv.get('sector') != 'XLV' or len(xlv.get('members', [])) != 10:
        raise RuntimeError('Healthcare live-stock universe is missing or incomplete')
    if xlv.get('generated_at') != json.loads(local['data/rrg-core.json']).get('generated_at'):
        raise RuntimeError('Healthcare stock data timestamp does not match core RRG data')
    for sec in STOCK_SECTORS:
        doc=json.loads(local[f'data/stocks/{sec}.json'])
        daily=doc['timeframes']['1D']['price_context']
        h4=doc['timeframes']['4H']['price_context']
        if set(daily)!=set(doc['members']) or set(h4)!=set(doc['members']):
            raise RuntimeError(f'{sec}: deployed price context incomplete')
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
    print(f'Live sync verified: {len(FILES)} exact files (including 11 stock files), 11/11 pairs, session {breadth["as_of"]}, journal {manifest["journal_status"]}')


if __name__ == '__main__':
    # GitHub Pages may report deployment before CDN edges serve the new build.
    # Keep exact file hashing, but allow more time for propagation.
    attempts = 10
    for attempt in range(attempts):
        try:
            verify(sys.argv[1])
            break
        except (RuntimeError, OSError, ValueError) as exc:
            print(f'Live verification attempt {attempt + 1}/{attempts}: {exc}', flush=True)
            if attempt == attempts - 1:
                raise SystemExit(1)
            time.sleep(15)
