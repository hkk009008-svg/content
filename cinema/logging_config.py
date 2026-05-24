"""Structured JSON logging configuration for the cinema pipeline.

`setup_logging()` installs a root logger that emits one JSON object per
log record to stdout. It is idempotent — safe to call from both
`web_server.py` (module load) and `cinema_pipeline.py` (when used as a
library) without doubling handlers.

Design notes:
- Custom 30-line formatter rather than `python-json-logger` to avoid the
  extra dependency. The formatter promotes any `extra={...}` kwargs into
  top-level JSON fields so structured fields (scene_id, shot_id, engine,
  pid, latency_ms, cost_usd, attempt, take_id) are queryable without
  string-parsing the message.
- Default level is INFO. Operators bump verbosity with the
  `CINEMA_LOG_LEVEL` env var (e.g. `CINEMA_LOG_LEVEL=DEBUG`).
- Noisy third-party libraries (DeepFace, tensorflow, matplotlib, PIL,
  urllib3) are pinned at WARNING so the operator log isn't drowned by
  library chatter. They keep their own levels if Set later.
- Exceptions inside an `except` block use `logger.exception(...)` which
  auto-captures the traceback. The JSON formatter embeds the formatted
  traceback under the `exc_info` field.

Caller-field convention (semantic distinctions worth knowing):
- ``shot_id`` / ``scene_id``: pipeline-assigned IDs, stable for the life
  of a project. Use these as the primary filter for "tell me what
  happened to shot X" log queries.
- ``stitched_path``: concatenated scene clips, BGM/voice not yet mixed.
  Emitted from ``_assemble_final``'s pre-mix stage.
- ``final_output``: post-BGM-mix output file. Emitted by the ffmpeg
  subprocess.run path inside ``_assemble_final``.
- ``final_path``: post-loudnorm, user-facing artifact. The value
  returned from ``CinemaPipeline.generate()``.
- ``stderr_tail``: last 200 chars of a subprocess's stderr. Decoded
  via ``bytes.decode("utf-8", errors="replace")`` so JSON consumers
  never see a ``b'...'`` repr in the stream.
- ``percent`` / ``stage`` / ``detail``: SSE-progress trail emitted by
  ``_default_progress``. The SSE callback path replaces this with the
  queue callback at runtime; logging is DEBUG-only so non-SSE callers
  don't double-emit when an adjacent explicit log already fired.

New fields are welcome — just avoid names colliding with
``_RESERVED_LOGRECORD_KEYS`` (those silently get dropped from the JSON
output by the formatter).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

# Default LogRecord attributes — anything NOT in this set is treated as
# `extra={...}` content and promoted to a top-level JSON field.
_RESERVED_LOGRECORD_KEYS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
}

_NOISY_LIBRARIES = ("DeepFace", "tensorflow", "matplotlib", "PIL", "urllib3")


class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record.

    Top-level keys: ts, level, logger, msg, plus any `extra={...}` fields
    the caller attached. If the record carries exc_info (i.e. inside an
    `except` after `logger.exception(...)`), the formatted traceback is
    written under the `exc_info` field.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOGRECORD_KEYS:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str | None = None) -> None:
    """Install the JSON formatter on the root logger. Idempotent.

    Args:
        level: Optional explicit level (e.g. "DEBUG"). If None, reads
            ``CINEMA_LOG_LEVEL`` from env, defaulting to "INFO".
    """
    resolved_level = (level or os.environ.get("CINEMA_LOG_LEVEL") or "INFO").upper()
    root = logging.getLogger()
    # Idempotent: clear any handlers we (or someone else) already added.
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(resolved_level)
    for noisy in _NOISY_LIBRARIES:
        logging.getLogger(noisy).setLevel(logging.WARNING)
