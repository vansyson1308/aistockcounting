"""Publish per-run agent metrics to CloudWatch (PutMetricData), best effort.

Enabled with CLOUDWATCH_METRICS_ENABLED=true on AWS; the instance role grants
``cloudwatch:PutMetricData``. Failures are logged and never affect a scan.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("app")
_client: Any = None


def metric_data(summary: dict[str, Any]) -> list[dict[str, Any]]:
    decision = summary["decision"]
    dims = [{"Name": "Service", "Value": "trayagent"}]
    return [
        {"MetricName": "AgentRuns", "Dimensions": dims, "Value": 1.0, "Unit": "Count"},
        {
            "MetricName": "AgentSteps",
            "Dimensions": dims,
            "Value": float(summary["steps_used"]),
            "Unit": "Count",
        },
        {
            "MetricName": "AgentLatencyMs",
            "Dimensions": dims,
            "Value": float(summary["elapsed_ms"]),
            "Unit": "Milliseconds",
        },
        {
            "MetricName": "Escalated",
            "Dimensions": dims,
            "Value": 1.0 if decision == "escalate" else 0.0,
            "Unit": "Count",
        },
        {
            "MetricName": "RecaptureRequested",
            "Dimensions": dims,
            "Value": 1.0 if decision == "request_recapture" else 0.0,
            "Unit": "Count",
        },
        {
            "MetricName": "PlannerFallbacks",
            "Dimensions": dims,
            "Value": float(summary.get("planner_fallbacks", 0)),
            "Unit": "Count",
        },
    ]


def publish(summary: dict[str, Any], namespace: str, region: str) -> None:
    def _send() -> None:
        global _client
        try:
            if _client is None:
                import boto3

                _client = boto3.client("cloudwatch", region_name=region)
            _client.put_metric_data(
                Namespace=namespace, MetricData=metric_data(summary)
            )
        except Exception:
            logger.warning("cloudwatch put_metric_data failed", exc_info=True)

    threading.Thread(target=_send, daemon=True).start()
