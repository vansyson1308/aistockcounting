from prometheus_client import Counter, Gauge, Histogram

request_count = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

inference_duration_seconds = Histogram(
    "inference_duration_seconds",
    "AI inference duration in seconds",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

model_loaded = Gauge(
    "model_loaded",
    "Whether the AI model is loaded (1) or not (0)",
)
