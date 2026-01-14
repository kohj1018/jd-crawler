#!/usr/bin/env python3
"""
Test script for Toss Job Groups API fetch.

This script tests the API fetch and parsing logic without Supabase.
Run from project root: python scripts/test_toss_fetch.py
"""

import hashlib
import json
import sys

import requests


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


def compute_list_hash(jobs: list[dict]) -> str:
    """Compute hash from (id, updated_at) pairs."""
    pairs = sorted((j.get("id", ""), j.get("updated_at", "")) for j in jobs)
    content = json.dumps(pairs, sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def main():
    print(f"[TEST] Fetching: {API_URL}")

    try:
        response = requests.get(API_URL, headers=API_HEADERS, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as e:
        print(f"[ERROR] Request failed: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON decode failed: {e}")
        sys.exit(1)

    if payload.get("resultType") != "SUCCESS":
        print(f"[ERROR] API returned: {payload.get('resultType')}")
        sys.exit(1)

    groups = payload.get("success", [])
    print(f"[OK] Fetched {len(groups)} job groups")

    # Extract primary jobs
    primary_jobs = []
    for group in groups:
        job = group.get("primary_job")
        if job:
            primary_jobs.append(job)

    print(f"[OK] Found {len(primary_jobs)} primary jobs")

    # Compute hash
    list_hash = compute_list_hash(primary_jobs)
    print(f"[OK] List hash: {list_hash[:16]}...")

    # Sample output
    print("\n--- Sample Jobs (first 3) ---")
    for i, group in enumerate(groups[:3]):
        job = group.get("primary_job")
        if not job:
            continue

        meta = meta_to_dict(job.get("metadata"))
        subsidiary = meta.get("포지션의 소속 자회사를 선택해 주세요.")
        company = f"Toss / {subsidiary}" if subsidiary else "Toss"

        print(f"\n[{i+1}] {job.get('title')}")
        print(f"    Company: {company}")
        print(f"    URL: {job.get('absolute_url')}")
        print(f"    Updated: {job.get('updated_at')}")

        location = (job.get("location") or {}).get("name", "N/A")
        print(f"    Location: {location}")

        jd_key = "Job Description을 작성해 주세요.(작성 전, 채용 커뮤니케이션 가이드 노션을 꼭 참고해 주세요.)"
        jd = meta.get(jd_key, "")
        if jd:
            # Show first 100 chars of JD
            preview = jd[:100].replace("\n", " ") + "..." if len(jd) > 100 else jd
            print(f"    JD Preview: {preview}")

    print("\n[TEST] Completed successfully!")


if __name__ == "__main__":
    main()
