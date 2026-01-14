from datetime import datetime, timezone
from typing import Any

from supabase import create_client, Client

from src.config import SUPABASE_URL, SUPABASE_SECRET_KEY


def get_client() -> Client:
    """Create and return a Supabase client."""
    return create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)


def get_active_targets(client: Client) -> list[dict[str, Any]]:
    """Fetch all active crawl targets."""
    response = client.table("crawl_targets").select("*").eq("is_active", True).execute()
    return response.data


def update_target_checked(client: Client, target_id: int) -> None:
    """Update last_checked_at for a target."""
    client.table("crawl_targets").update({
        "last_checked_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", target_id).execute()


def update_target_hash(client: Client, target_id: int, new_hash: str) -> None:
    """Update last_list_hash and last_checked_at for a target."""
    client.table("crawl_targets").update({
        "last_list_hash": new_hash,
        "last_checked_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", target_id).execute()


def upsert_job_posting(
    client: Client,
    target_id: int,
    title: str,
    company_name: str,
    content_raw: str,
    original_url: str,
) -> str:
    """
    Upsert a job posting.
    Returns 'NEW', 'UPDATED', or 'SKIP' based on what happened.
    """
    existing = (
        client.table("job_postings")
        .select("id, content_raw")
        .eq("original_url", original_url)
        .execute()
    )

    now = datetime.now(timezone.utc).isoformat()

    if existing.data:
        old_content = existing.data[0].get("content_raw", "")
        if old_content == content_raw:
            return "SKIP"

        client.table("job_postings").update({
            "title": title,
            "company_name": company_name,
            "content_raw": content_raw,
            "updated_at": now,
        }).eq("original_url", original_url).execute()
        return "UPDATED"
    else:
        client.table("job_postings").insert({
            "crawl_target_id": target_id,
            "title": title,
            "company_name": company_name,
            "content_raw": content_raw,
            "original_url": original_url,
            "analysis_result": None,
            "created_at": now,
            "updated_at": now,
        }).execute()
        return "NEW"
