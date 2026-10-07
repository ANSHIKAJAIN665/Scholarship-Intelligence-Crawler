#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crawler.crawler import execute_new_crawl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover and verify scholarships from configured official sources.")
    parser.add_argument(
        "--interval-hours",
        type=float,
        help="Repeat the live crawl every N hours until interrupted. Omit to run once.",
    )
    args = parser.parse_args()
    if args.interval_hours is not None and args.interval_hours <= 0:
        parser.error("--interval-hours must be greater than zero")
    try:
        while True:
            run = execute_new_crawl()
            print(
                f"Run {run.id}: {run.status}; discovered={run.discovered_count}, "
                f"new={run.new_count}, updated={run.updated_count}, changed={run.changed_count}, "
                f"expired={run.expired_count}, failed={run.failed_count}"
            )
            if run.message:
                print(run.message)
            if args.interval_hours is None:
                return 0 if run.status != "FAILED" else 1
            time.sleep(args.interval_hours * 3600)
    except KeyboardInterrupt:
        print("Scheduled crawling stopped.")
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
