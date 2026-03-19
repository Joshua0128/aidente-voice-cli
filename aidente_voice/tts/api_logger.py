"""JSONL logger for outgoing TTS API calls."""

import json
from datetime import datetime, timezone
from pathlib import Path


def append_log(
    log_path: Path,
    *,
    endpoint: str,
    request: dict,
    status: int,
    response_bytes: int | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> None:
    """Append one log entry to a JSONL file (one JSON object per line).

    Creates the file and parent directories if they don't exist.
    Safe for concurrent writes within the same process (GIL-protected append).
    """
    entry: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "request": request,
        "status": status,
    }
    if response_bytes is not None:
        entry["bytes"] = response_bytes
    if duration_ms is not None:
        entry["duration_ms"] = duration_ms
    if error is not None:
        entry["error"] = error

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
