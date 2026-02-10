"""
Kakao Careers API Parser.

Fetches job postings from Kakao's public careers REST API.
Must iterate over 4 job categories (parts) with pagination (15 per page).
"""

import hashlib
import json
from typing import Any

import requests
from supabase import Client

from src.db import update_target_checked, update_target_hash, update_target_error, upsert_job_posting


API_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

REQUEST_TIMEOUT = 30

# Kakao groups jobs into these 4 categories; no "all" option exists.
JOB_PARTS = ["TECHNOLOGY", "BUSINESS_SERVICES", "STAFF", "DESIGN"]


def _compute_list_hash(jobs: list[dict]) -> str:
    """Compute a hash from (realId, uptDate) pairs."""
    pairs = sorted((j.get("realId", ""), j.get("uptDate", "")) for j in jobs)
    content = json.dumps(pairs, sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _fetch_all_jobs(base_url: str) -> list[dict]:
    """
    Fetch all jobs across all parts and pages.

    Returns:
        Combined list of all job objects.
    """
    all_jobs: list[dict] = []

    for part in JOB_PARTS:
        page = 1
        while True:
            params = {"part": part, "page": page}
            response = requests.get(
                base_url, params=params, headers=API_HEADERS, timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            payload = response.json()

            job_list = payload.get("jobList", [])
            all_jobs.extend(job_list)

            total_page = payload.get("totalPage", 1)
            if page >= total_page:
                break
            page += 1

    return all_jobs


def _build_content_raw(job: dict) -> str:
    """Build content_raw JSON string from job data."""
    skills = [s.get("skillSetName") for s in (job.get("skillSetList") or []) if s.get("skillSetName")]

    content = {
        "job_part": job.get("jobPartName"),
        "company_name": job.get("companyName"),
        "company_name_en": job.get("companyNameEn"),
        "location": job.get("locationName"),
        "location_en": job.get("locationNameEn"),
        "employee_type": job.get("employeeTypeName"),
        "employee_type_en": job.get("employeeTypeNameEn"),
        "work_type": job.get("workTypeName"),
        "recruit_count": job.get("recruitCount"),
        "reg_date": job.get("regDate"),
        "updated_at": job.get("uptDate"),
        "end_date": job.get("endDate"),
        "skills": skills,
        "introduction": job.get("introduction", ""),
        "work_content": job.get("workContentDesc", ""),
        "qualification": job.get("qualification", ""),
        "hiring_process": job.get("jobOfferProcessDesc", ""),
        "krew_comment": job.get("krewComment", ""),
        "raw": job,
    }
    return json.dumps(content, ensure_ascii=False)


def crawl_kakao_api(client: Client, target: dict[str, Any]) -> dict[str, int]:
    """
    Crawl Kakao careers API and upsert job postings.

    Args:
        client: Supabase client
        target: Target record from crawl_targets table

    Returns:
        Stats dict with counts for NEW, UPDATED, SKIP, ERROR
    """
    stats = {"NEW": 0, "UPDATED": 0, "SKIP": 0, "ERROR": 0}

    target_id = target["id"]
    target_name = target.get("company_name") or target.get("name", f"target_{target_id}")
    api_url = target["list_url"]
    last_list_hash = target.get("last_list_hash")

    print(f"[INFO] Processing target: {target_name} (API: {api_url})")

    # Fetch all jobs across all parts and pages
    try:
        all_jobs = _fetch_all_jobs(api_url)
    except requests.RequestException as e:
        error_msg = f"Failed to fetch API: {e}"
        print(f"[ERROR] Kakao: {error_msg}")
        update_target_error(client, target_id, error_msg)
        stats["ERROR"] += 1
        return stats
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON response: {e}"
        print(f"[ERROR] Kakao: {error_msg}")
        update_target_error(client, target_id, error_msg)
        stats["ERROR"] += 1
        return stats

    if not all_jobs:
        print(f"[WARN] No jobs found for {target_name}")
        update_target_checked(client, target_id)
        return stats

    print(f"[INFO] Fetched {len(all_jobs)} total jobs from Kakao API")

    # Compute hash and check for changes
    current_hash = _compute_list_hash(all_jobs)

    if current_hash == last_list_hash:
        print(f"[SKIP] No changes detected for {target_name} (unchanged)")
        update_target_checked(client, target_id)
        return stats

    print(f"[INFO] Changes detected for {target_name}, upserting {len(all_jobs)} jobs...")

    # Process each job
    for job in all_jobs:
        real_id = job.get("realId")
        if not real_id:
            continue

        original_url = f"https://careers.kakao.com/jobs/{real_id}"

        try:
            company_name = job.get("companyName", "카카오")
            content_raw = _build_content_raw(job)
            title = job.get("jobOfferTitle", "Untitled")

            result = upsert_job_posting(
                client=client,
                target_id=target_id,
                title=title,
                company_name=company_name,
                content_raw=content_raw,
                original_url=original_url,
            )

            stats[result] += 1
            print(f"[{result}] {title}")

        except Exception as e:
            job_title = job.get("jobOfferTitle", "unknown")
            print(f"[ERROR] Kakao: Failed to process job '{job_title}': {e}")
            stats["ERROR"] += 1

    # Update target hash after successful crawl
    update_target_hash(client, target_id, current_hash)
    print(f"[UPSERT] Kakao: {stats['NEW']} new, {stats['UPDATED']} updated, {stats['SKIP']} skipped")

    return stats
