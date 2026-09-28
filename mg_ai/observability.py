import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("mg.audit")
FIELDS = {"request_id", "client", "route", "provider", "model", "attempt", "result",
          "error_category", "latency_ms", "usage", "cost_estimate_usd", "cost_class",
          "upstream_model", "fallback_count", "candidate_sequence"}


def emit(**metadata: Any) -> None:
    record = {k: v for k, v in metadata.items() if k in FIELDS}
    record["timestamp"] = datetime.now(timezone.utc).isoformat()
    logger.info(json.dumps(record, ensure_ascii=True, allow_nan=False))
