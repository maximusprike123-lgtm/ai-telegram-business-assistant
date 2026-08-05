"""Bounded HTTP load probe for a disposable release-candidate deployment."""

from __future__ import annotations

import argparse
import asyncio
import json
from statistics import median, quantiles
from time import monotonic

import httpx


async def run(base_url: str, api_key: str, path: str, requests: int, concurrency: int) -> int:
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    failures = 0

    async with httpx.AsyncClient(base_url=base_url, timeout=20) as client:

        async def issue() -> None:
            nonlocal failures
            async with semaphore:
                started = monotonic()
                response = await client.get(path, headers={"X-Internal-API-Key": api_key})
                latencies.append((monotonic() - started) * 1000)
                failures += int(response.status_code >= 400)

        started = monotonic()
        await asyncio.gather(*(issue() for _ in range(requests)))
        elapsed = monotonic() - started

    ordered = sorted(latencies)
    cuts = quantiles(ordered, n=100, method="inclusive") if len(ordered) > 1 else ordered * 99
    print(
        json.dumps(
            {
                "path": path,
                "requests": requests,
                "concurrency": concurrency,
                "failures": failures,
                "throughput_per_second": round(requests / elapsed, 2),
                "latency_ms": {
                    "median": round(median(ordered), 2),
                    "p95": round(cuts[94], 2),
                    "p99": round(cuts[98], 2),
                },
            },
            sort_keys=True,
        )
    )
    return int(failures > 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--path", default="/api/v1/catalog/services")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.requests <= 10_000 or not 1 <= args.concurrency <= 200:
        parser.error("requests must be 1-10000 and concurrency must be 1-200")
    return asyncio.run(run(args.base_url, args.api_key, args.path, args.requests, args.concurrency))


if __name__ == "__main__":
    raise SystemExit(main())
