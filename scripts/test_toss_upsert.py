#!/usr/bin/env python3
"""
Test script for Toss Job Groups API upsert to Supabase.

This script fetches from Toss API and upserts to job_postings table.
Run from project root: python scripts/test_toss_upsert.py

Prerequisites:
- .env file with SUPABASE_URL and SUPABASE_SECRET_KEY
- job_postings.original_url must have UNIQUE constraint

If UNIQUE constraint is missing, you'll see an error like:
  "duplicate key value violates unique constraint" or
  "there is no unique or exclusion constraint matching the ON CONFLICT"

Fix with:
  ALTER TABLE job_postings ADD CONSTRAINT job_postings_original_url_key UNIQUE (original_url);
"""

import json
import os
import sys

from dotenv import load_dotenv
import requests
from supabase import create_client

# Load environment variables
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SECRET_KEY:
    print("[ERROR] Missing SUPABASE_URL or SUPABASE_SECRET_KEY in environment")
    sys.exit(1)

print(f"[INFO] Supabase URL: {SUPABASE_URL}")

API_URL = "https://api-public.toss.im/api/v3/ipd-eggnog/career/job-groups"
API_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def meta_to_dict(metadata: list[dict] | None) -> dict:
    """Convert metadata list to dict."""
    result = {}
    for m in metadata or []:
        name = m.get("name")
        if name:
            result[name] = m.get("value")
    return result


def build_content_raw(group: dict, job: dict, meta: dict) -> str:
    """Build content_raw JSON string."""
    jd_key = "Job Description을 작성해 주세요.(작성 전, 채용 커뮤니케이션 가이드 노션을 꼭 참고해 주세요.)"
    content = {
        "job_group_title": group.get("title"),
        "location": (job.get("location") or {}).get("name"),
        "requisition_id": job.get("requisition_id"),
        "first_published": job.get("first_published"),
        "updated_at": job.get("updated_at"),
        "employment_type": meta.get("Employment_Type"),
        "job_category": meta.get("커리어 페이지 노출 Job Category 값을 선택해주세요"),
        "keywords_external": meta.get(
            "외부 노출용 키워드를 입력해주세요. (최대 4개  / 1번 키워드 = 포지션 카테고리 / 나머지 키워드 = 포지션 특성에 맞게 작성)"
        ),
        "keywords_search": meta.get(
            "검색에 쓰일 키워드를 입력해주세요(신규 비즈니스의 초기멤버라면, 초기멤버 키워드를 작성하세요)"
        ),
        "description_markdown": meta.get(jd_key, ""),
        "raw": job,
    }
    return json.dumps(content, ensure_ascii=False)


def main():
    print(f"\n[STEP 1] Fetching Toss API: {API_URL}")

    try:
        response = requests.get(API_URL, headers=API_HEADERS, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as e:
        print(f"[ERROR] Request failed: {e}")
        sys.exit(1)

    if payload.get("resultType") != "SUCCESS":
        print(f"[ERROR] API returned: {payload.get('resultType')}")
        sys.exit(1)

    groups = payload.get("success", [])
    print(f"[OK] Fetched {len(groups)} job groups")

    # Build rows for upsert
    print("\n[STEP 2] Building upsert rows...")
    rows = []

    for group in groups:
        job = group.get("primary_job")
        if not job:
            continue

        original_url = job.get("absolute_url")
        if not original_url:
            continue

        meta = meta_to_dict(job.get("metadata"))
        subsidiary = meta.get("포지션의 소속 자회사를 선택해 주세요.")
        company_name = f"Toss / {subsidiary}" if subsidiary else "Toss"

        rows.append({
            "title": job.get("title", "Untitled"),
            "company_name": company_name,
            "content_raw": build_content_raw(group, job, meta),
            "original_url": original_url,
            "analysis_result": None,
        })

    print(f"[OK] Built {len(rows)} rows for upsert")

    # Upsert to Supabase
    print("\n[STEP 3] Upserting to Supabase...")
    try:
        sb = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
        result = sb.table("job_postings").upsert(
            rows,
            on_conflict="original_url"
        ).execute()
        print(f"[OK] UPSERTED {len(rows)}")
    except Exception as e:
        error_str = str(e)
        # Mask any potential key leakage in error
        if SUPABASE_SECRET_KEY and SUPABASE_SECRET_KEY in error_str:
            error_str = error_str.replace(SUPABASE_SECRET_KEY, "***MASKED***")
        print(f"[ERROR] Upsert failed: {error_str}")

        if "unique" in error_str.lower() or "conflict" in error_str.lower():
            print("\n[HINT] Missing UNIQUE constraint on original_url?")
            print("Run this SQL in Supabase SQL Editor:")
            print("  ALTER TABLE job_postings ADD CONSTRAINT job_postings_original_url_key UNIQUE (original_url);")
        sys.exit(1)

    print("\n[DONE] Upsert completed successfully!")


if __name__ == "__main__":
    main()
