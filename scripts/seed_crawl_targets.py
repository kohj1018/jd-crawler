#!/usr/bin/env python3
"""
Seed script for crawl_targets table.

Adds Toss job groups API target to crawl_targets.
Run from project root: python scripts/seed_crawl_targets.py

Prerequisites:
- .env file with SUPABASE_URL and SUPABASE_SECRET_KEY
"""

import os
import sys

from dotenv import load_dotenv
from supabase import create_client

# Load environment variables
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    print("[ERROR] Missing SUPABASE_URL or SUPABASE_SECRET_KEY in environment")
    sys.exit(1)

# Toss target configuration
TOSS_TARGET = {
    "company_name": "Toss",
    "list_url": "https://api-public.toss.im/api/v3/ipd-eggnog/career/job-groups",
    "parser_type": "toss_job_groups_api",
    "is_active": True,
    "last_list_hash": None,
    "last_checked_at": None,
    "last_error": None,
}


def main():
    print(f"[INFO] Supabase URL: {SUPABASE_URL}")
    print("[INFO] Seeding crawl_targets table...")

    try:
        sb = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

        # Check if Toss target already exists
        existing = (
            sb.table("crawl_targets")
            .select("id")
            .eq("company_name", TOSS_TARGET["company_name"])
            .eq("parser_type", TOSS_TARGET["parser_type"])
            .execute()
        )

        if existing.data:
            print(f"[SKIP] Toss target already exists (id={existing.data[0]['id']})")
            return

        # Insert new target
        result = sb.table("crawl_targets").insert(TOSS_TARGET).execute()

        if result.data:
            print(f"[OK] Toss target inserted (id={result.data[0]['id']})")
        else:
            print("[OK] Toss target inserted")

    except Exception as e:
        print(f"[ERROR] Failed to seed crawl_targets: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
