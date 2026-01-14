#!/usr/bin/env python3
"""
Job Postings Crawler

Crawls job posting sites defined in Supabase crawl_targets table
and stores results in job_postings table.

Usage:
    python -m src.main

Environment variables required:
    SUPABASE_URL: Your Supabase project URL
    SUPABASE_SERVICE_ROLE_KEY: Your Supabase service role key
"""

import sys
from datetime import datetime, timezone

from src.db import get_client, get_active_targets
from src.crawler import crawl_all


def main() -> int:
    """Main entry point."""
    print("=" * 60)
    print(f"Job Crawler started at {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # Initialize Supabase client
    try:
        client = get_client()
    except Exception as e:
        print(f"[FATAL] Failed to initialize Supabase client: {e}")
        return 1

    # Get active targets
    try:
        targets = get_active_targets(client)
    except Exception as e:
        print(f"[FATAL] Failed to fetch crawl targets: {e}")
        return 1

    print(f"[INFO] Active crawl targets: {len(targets)}")

    if not targets:
        print("[INFO] No records found in crawl_targets where is_active=true")
        print("[HINT] Run: python scripts/seed_crawl_targets.py")
        return 0
    print("-" * 60)

    # Crawl all targets
    stats = crawl_all(client, targets)

    # Print summary
    print("=" * 60)
    print("Crawl Summary:")
    print(f"  - NEW:     {stats['NEW']}")
    print(f"  - UPDATED: {stats['UPDATED']}")
    print(f"  - SKIP:    {stats['SKIP']}")
    print(f"  - ERROR:   {stats['ERROR']}")
    print("=" * 60)
    print(f"Job Crawler finished at {datetime.now(timezone.utc).isoformat()}")

    # Return non-zero if there were errors
    return 1 if stats["ERROR"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
