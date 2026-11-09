"""File-logging for rejected /api writes.

[api-reject] lines go to stdout (for `podman logs food-dashboard`) and are
appended to data/api_reject.log, so rejected writes stay diagnosable from a
plain repo checkout — mounted volumes, no container access needed.
Override the path with the API_REJECT_LOG env var.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MAX_LOG_BYTES = 1 << 20  # rotation cap: the log stays bounded


def log_path() -> Path:
    env = os.environ.get("API_REJECT_LOG")
    return Path(env) if env else REPO_ROOT / "data" / "api_reject.log"


def reject_line(method: str, path: str, status: int, body: bytes) -> str:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"{ts} [api-reject] {method} {path} -> {status}"
    if body:
        text = " ".join(body.decode("utf-8", "replace").split())[:800]
        line += f"\n  body: {text}"
    return line + "\n"


def append_reject(method: str, path: str, status: int, body: bytes) -> None:
    """Best effort — reject logging must never break the request path."""
    try:
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        entry = reject_line(method, path, status, body)
        if p.exists() and p.stat().st_size > MAX_LOG_BYTES:
            p.write_text("# api_reject.log rotated (1 MiB cap)\n", encoding="utf-8")
        with p.open("a", encoding="utf-8") as fh:
            fh.write(entry)
    except OSError:
        pass
