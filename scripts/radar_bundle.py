"""Private radar input bundle, captured from the dashboard build itself.

Only active when RADAR_BUNDLE_OUT is set; otherwise the build behaves exactly as
before. For each timeframe the bundle keeps the OHLCV rows of the very download
(batch, individual retry or lagging-close refresh) that produced each symbol's
validated close series, restricted to those validated completed bars. Every
exported close must equal the validated close; any mismatch withholds the symbol.
The file is written outside _site and must never be published.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

FIELDS = ("Open", "High", "Low", "Close", "Volume")
SCHEMA = "radar-input-v1"
_frames: dict = {}
_withheld: dict = {}


def enabled() -> bool:
    return bool(os.environ.get("RADAR_BUNDLE_OUT"))


def ohlcv_block(downloaded: pd.DataFrame, ticker: str) -> pd.DataFrame:
    if isinstance(downloaded.columns, pd.MultiIndex):
        lv0 = downloaded.columns.get_level_values(0)
        block = downloaded[ticker] if ticker in lv0 else downloaded.xs(ticker, axis=1, level=1)
    else:
        block = downloaded
    missing = [f for f in FIELDS if f not in block.columns]
    if missing:
        raise ValueError(f"missing fields {missing}")
    return block[list(FIELDS)]


def capture(label: str, closes: dict, sources: dict) -> None:
    """Record validated OHLCV for one timeframe. Called after all build-time checks."""
    if not enabled() or label not in ("1D", "1H"):
        return
    out, held = {}, {}
    for ticker, series in closes.items():
        s = series.dropna()
        try:
            block = ohlcv_block(sources[ticker], ticker).reindex(s.index)
            if block.isna().any().any():
                raise ValueError("OHLCV gaps on validated bars")
            if not np.allclose(block["Close"].to_numpy(float), s.to_numpy(float), rtol=0, atol=1e-9):
                raise ValueError("exported close differs from validated close")
            out[ticker] = [[t.isoformat(), *[float(v) for v in row]] for t, row in zip(block.index, block.to_numpy())]
        except Exception as exc:  # withheld, never patched or filled
            held[ticker] = f"{type(exc).__name__}: {exc}"
    _frames[label] = out
    _withheld[label] = held


def write(session: str, generated_at: str, extra: dict) -> Path | None:
    if not enabled():
        return None
    path = Path(os.environ["RADAR_BUNDLE_OUT"])
    if "_site" in path.resolve().parts:
        raise RuntimeError("radar bundle must never be written inside _site")
    payload = {"schema": SCHEMA, "session": session, "generated_at": generated_at,
               "commit": os.environ.get("GITHUB_SHA", "local"), "fields": ["time", *FIELDS],
               "frames": _frames, "withheld": _withheld, **extra}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(raw, mtime=0))
    Path(str(path) + ".sha256").write_text(hashlib.sha256(raw).hexdigest() + "\n")
    print(f"radar bundle written: session {session}, "
          + ", ".join(f"{k}={len(v)} symbols" for k, v in _frames.items())
          + f", withheld={sum(len(v) for v in _withheld.values())}")
    return path
