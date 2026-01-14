"""
Toss Job Groups API Parser.

This parser fetches job postings from Toss's internal API instead of HTML pages.
It's a specialized parser that handles the entire crawl flow internally.
"""

import hashlib
import json
from typing import Any

import requests
from supabase import Client

from src.db import update_target_checked, update_target_hash, update_target_error, upsert_job_posting


API_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

REQUEST_TIMEOUT = 30


def _meta_to_dict(metadata: list[dict] | None) -> dict[str, Any]:
    """Convert metadata list to a dict keyed by name."""
    result: dict[str, Any] = {}
    for m in metadata or []:
        name = m.get("name")
        if name:
            result[name] = m.get("value")
    return result


def _compute_list_hash(jobs: list[dict]) -> str:
    """
    Compute a hash from (job.id, job.updated_at) pairs.
    Used to detect changes in the job list.
    """
    pairs = sorted((j.get("id", ""), j.get("updated_at", "")) for j in jobs)
    content = json.dumps(pairs, sort_keys=True)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _build_company_name(meta: dict[str, Any]) -> str:
    """Build company name from metadata."""
    subsidiary = meta.get("포지션의 소속 자회사를 선택해 주세요.")
    if subsidiary:
        return f"Toss / {subsidiary}"
    return "Toss"


def _build_content_raw(group: dict, job: dict, meta: dict[str, Any]) -> str:
    """Build content_raw JSON string from job data."""
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


def crawl_toss_api(client: Client, target: dict[str, Any]) -> dict[str, int]:
    """
    Crawl Toss job groups API and upsert job postings.

    Args:
        client: Supabase client
        target: Target record from crawl_targets table

    Returns:
        Stats dict with counts for NEW, UPDATED, SKIP, ERROR
    """
    stats = {"NEW": 0, "UPDATED": 0, "SKIP": 0, "ERROR": 0}

    target_id = target["id"]
    target_name = target.get("name", f"target_{target_id}")
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
        print(f"[ERROR] Toss: {error_msg}")
        update_target_error(client, target_id, error_msg)
        stats["ERROR"] += 1
        return stats
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON response: {e}"
        print(f"[ERROR] Toss: {error_msg}")
        update_target_error(client, target_id, error_msg)
        stats["ERROR"] += 1
        return stats

    # Validate response
    if payload.get("resultType") != "SUCCESS":
        error_msg = f"API returned non-SUCCESS: {payload.get('resultType')}"
        print(f"[ERROR] Toss: {error_msg}")
        update_target_error(client, target_id, error_msg)
        stats["ERROR"] += 1
        return stats

    groups = payload.get("success", [])
    if not groups:
        print(f"[WARN] No job groups found for {target_name}")
        update_target_checked(client, target_id)
        return stats

    # Extract primary_jobs for hash computation
    primary_jobs = [g.get("primary_job") for g in groups if g.get("primary_job")]
    current_hash = _compute_list_hash(primary_jobs)

    # Check if list has changed
    if current_hash == last_list_hash:
        print(f"[SKIP] No changes detected for {target_name} (unchanged)")
        update_target_checked(client, target_id)
        return stats

    print(f"[INFO] Changes detected for {target_name}, upserting {len(primary_jobs)} jobs...")

    # Process each job group
    for group in groups:
        job = group.get("primary_job")
        if not job:
            continue

        original_url = job.get("absolute_url")
        if not original_url:
            print(f"[WARN] Missing absolute_url for job in group: {group.get('title')}")
            continue

        try:
            meta = _meta_to_dict(job.get("metadata"))
            company_name = _build_company_name(meta)
            content_raw = _build_content_raw(group, job, meta)
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
            print(f"[ERROR] Toss: Failed to process job '{job_title}': {e}")
            stats["ERROR"] += 1

    # Update target hash after successful crawl
    update_target_hash(client, target_id, current_hash)
    print(f"[UPSERT] Toss: {stats['NEW']} new, {stats['UPDATED']} updated, {stats['SKIP']} skipped")

    return stats
