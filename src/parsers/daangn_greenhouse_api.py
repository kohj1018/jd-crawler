"""
Daangn (당근) Greenhouse API Parser.

Fetches job postings from Daangn's Greenhouse board API.
API docs: https://developers.greenhouse.io/harvest.html#list-jobs
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


def _compute_list_hash(jobs: list[dict]) -> str:
    """Compute a hash from (job.id, job.updated_at) pairs."""
    pairs = sorted((str(j.get("id", "")), j.get("updated_at", "")) for j in jobs)
    content = json.dumps(pairs, sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _meta_to_dict(metadata: list[dict] | None) -> dict[str, Any]:
    """Convert Greenhouse metadata list to a dict keyed by name."""
    result: dict[str, Any] = {}
    for m in metadata or []:
        name = m.get("name")
        if name:
            result[name] = m.get("value")
    return result


def _build_company_name(meta: dict[str, Any]) -> str:
    """Build company name from metadata."""
    corporate = meta.get("Corporate")
    if corporate and corporate != "당근마켓":
        return f"당근 / {corporate}"
    return "당근"


def _build_content_raw(job: dict, meta: dict[str, Any]) -> str:
    """Build content_raw JSON string from job data."""
    departments = [d.get("name") for d in job.get("departments", []) if d.get("name")]

    content = {
        "location": (job.get("location") or {}).get("name"),
        "departments": departments,
        "first_published": job.get("first_published"),
        "updated_at": job.get("updated_at"),
        "requisition_id": job.get("requisition_id"),
        "employment_type": meta.get("Employment Type"),
        "prior_experience": meta.get("Prior Experience"),
        "alternative_civilian_service": meta.get("Alternative Civilian Service"),
        "keywords": meta.get("Keywords"),
        "description_html": job.get("content", ""),
        "raw": job,
    }
    return json.dumps(content, ensure_ascii=False)


def crawl_daangn_api(client: Client, target: dict[str, Any]) -> dict[str, int]:
    """
    Crawl Daangn Greenhouse API and upsert job postings.

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

    # Fetch API
    try:
        response = requests.get(api_url, headers=API_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as e:
        error_msg = f"Failed to fetch API: {e}"
        print(f"[ERROR] Daangn: {error_msg}")
        update_target_error(client, target_id, error_msg)
        stats["ERROR"] += 1
        return stats
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON response: {e}"
        print(f"[ERROR] Daangn: {error_msg}")
        update_target_error(client, target_id, error_msg)
        stats["ERROR"] += 1
        return stats

    # Extract jobs
    jobs = payload.get("jobs", [])
    if not jobs:
        print(f"[WARN] No jobs found for {target_name}")
        update_target_checked(client, target_id)
        return stats

    # Compute hash and check for changes
    current_hash = _compute_list_hash(jobs)

    if current_hash == last_list_hash:
        print(f"[SKIP] No changes detected for {target_name} (unchanged)")
        update_target_checked(client, target_id)
        return stats

    print(f"[INFO] Changes detected for {target_name}, upserting {len(jobs)} jobs...")

    # Process each job
    for job in jobs:
        job_id = job.get("id")
        if not job_id:
            continue

        original_url = f"https://about.daangn.com/jobs/{job_id}/"

        try:
            meta = _meta_to_dict(job.get("metadata"))
            company_name = _build_company_name(meta)
            content_raw = _build_content_raw(job, meta)
            title = job.get("title", "Untitled")

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
            job_title = job.get("title", "unknown")
            print(f"[ERROR] Daangn: Failed to process job '{job_title}': {e}")
            stats["ERROR"] += 1

    # Update target hash after successful crawl
    update_target_hash(client, target_id, current_hash)
    print(f"[UPSERT] Daangn: {stats['NEW']} new, {stats['UPDATED']} updated, {stats['SKIP']} skipped")

    return stats
