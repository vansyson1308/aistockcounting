#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.inference import InferenceService


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True)
    args = p.parse_args()

    img_path = Path(args.image)
    if not img_path.exists():
        raise SystemExit(f"Image not found: {img_path}")

    payload = img_path.read_bytes()
    service = InferenceService()
    result = asyncio.run(service.predict(payload))

    print(f"detected_count={result['detected_count']}")
    print(f"confidence_avg={result['confidence_avg']}")
    print(f"processing_time_ms={result['processing_time_ms']}")
    print(f"boxes={result['boxes']}")


if __name__ == "__main__":
    main()
