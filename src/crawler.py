import hashlib
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from supabase import Client

from src.config import REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY, USER_AGENT
from src.db import (
    update_target_checked,
    update_target_hash,
    upsert_job_posting,
)
from src.parsers import get_parser
from src.parsers.base import JobItem
from src.parsers.toss_job_groups_api import crawl_toss_api
from src.parsers.daangn_greenhouse_api import crawl_daangn_api
from src.parsers.kakao_api import crawl_kakao_api

# Parser types that use API-based crawling instead of HTML parsing
API_PARSER_TYPES = {"toss_job_groups_api", "daangn_greenhouse_api", "kakao_api"}


@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=RETRY_DELAY, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    reraise=True,
)
def fetch_url(url: str) -> str:
    """
    Fetch a URL with retry logic.

    Args:
        url: The URL to fetch

    Returns:
        The response text

    Raises:
        httpx.HTTPError: If all retries fail
    """
    with httpx.Client(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
        return response.text


def compute_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def crawl_target(client: Client, target: dict[str, Any]) -> dict[str, int]:
    """
    Crawl a single target and process its job postings.

    Args:
        client: Supabase client
        target: Target record from crawl_targets table

    Returns:
        Stats dict with counts for NEW, UPDATED, SKIP, ERROR
    """
    parser_type = target.get("parser_type", "generic")

    # Dispatch to API-based crawlers
    if parser_type in API_PARSER_TYPES:
        if parser_type == "toss_job_groups_api":
            return crawl_toss_api(client, target)
        elif parser_type == "daangn_greenhouse_api":
            return crawl_daangn_api(client, target)
        elif parser_type == "kakao_api":
            return crawl_kakao_api(client, target)

    stats = {"NEW": 0, "UPDATED": 0, "SKIP": 0, "ERROR": 0}

    target_id = target["id"]
    target_name = target.get("name", f"target_{target_id}")
    list_url = target["list_url"]
    parser_config = target.get("parser_config") or {}
    last_list_hash = target.get("last_list_hash")

    print(f"[INFO] Processing target: {target_name} ({list_url})")

    # Fetch list page
    try:
        list_html = fetch_url(list_url)
    except Exception as e:
        print(f"[ERROR] Failed to fetch list URL for {target_name}: {e}")
        stats["ERROR"] += 1
        return stats

    # Get parser and normalize HTML
    try:
        parser = get_parser(parser_type, parser_config)
    except ValueError as e:
        print(f"[ERROR] {e}")
        stats["ERROR"] += 1
        return stats

    normalized_html = parser.normalize_html(list_html)
    current_hash = compute_hash(normalized_html)

    # Check if list has changed
    if current_hash == last_list_hash:
        print(f"[SKIP] No changes detected for {target_name}")
        update_target_checked(client, target_id)
        return stats

    print(f"[INFO] Changes detected for {target_name}, parsing job list...")

    # Parse job list
    try:
        job_items: list[JobItem] = parser.parse_list(list_html)
    except Exception as e:
        print(f"[ERROR] Failed to parse list for {target_name}: {e}")
        stats["ERROR"] += 1
        return stats

    if not job_items:
        print(f"[WARN] No job items found for {target_name}")
        update_target_hash(client, target_id, current_hash)
        return stats

    print(f"[INFO] Found {len(job_items)} job items for {target_name}")

    # Process each job item
    for item in job_items:
        try:
            # Fetch detail page
            detail_html = fetch_url(item.url)
            content_raw = parser.parse_detail(detail_html)

            if not content_raw:
                print(f"[WARN] Empty content for: {item.title}")
                continue

            # Upsert to database
            result = upsert_job_posting(
                client=client,
                target_id=target_id,
                title=item.title,
                company_name=item.company_name,
                content_raw=content_raw,
                original_url=item.url,
            )

            stats[result] += 1
            print(f"[{result}] {item.title} ({item.url})")

        except Exception as e:
            print(f"[ERROR] Failed to process {item.title}: {e}")
            stats["ERROR"] += 1

    # Update target hash after successful crawl
    update_target_hash(client, target_id, current_hash)

    return stats


def crawl_all(client: Client, targets: list[dict[str, Any]]) -> dict[str, int]:
    """
    Crawl all targets and aggregate stats.

    Args:
        client: Supabase client
        targets: List of target records

    Returns:
        Aggregated stats dict
    """
    total_stats = {"NEW": 0, "UPDATED": 0, "SKIP": 0, "ERROR": 0}

    for target in targets:
        target_stats = crawl_target(client, target)
        for key in total_stats:
            total_stats[key] += target_stats[key]

    return total_stats
