# scripts/seed_toss_jobs_to_supabase.py
import os, json, requests
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]  # sb_secret_...
sb = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

API_URL = "https://api-public.toss.im/api/v3/ipd-eggnog/career/job-groups"

def meta_to_dict(metadata: list[dict]) -> dict:
    # name이 길고 한글이 섞여 있어서 dict로 바꿔두면 나중에 쓰기 편함
    d = {}
    for m in metadata or []:
        name = m.get("name")
        val = m.get("value")
        if name:
            d[name] = val
    return d

r = requests.get(
    API_URL,
    headers={"Accept": "application/json", "Accept-Encoding": "gzip, deflate", "User-Agent": "Mozilla/5.0"},
    timeout=20,
)
r.raise_for_status()
payload = r.json()
assert payload["resultType"] == "SUCCESS"

rows = []
for g in payload["success"]:
    job = g.get("primary_job")
    if not job:
        continue

    meta = meta_to_dict(job.get("metadata", []))
    subsidiary = meta.get("포지션의 소속 자회사를 선택해 주세요.")
    company_name = f"Toss / {subsidiary}" if subsidiary else "Toss"

    jd = meta.get("Job Description을 작성해 주세요.(작성 전, 채용 커뮤니케이션 가이드 노션을 꼭 참고해 주세요.)", "")

    content = {
        "job_group_title": g.get("title"),
        "location": (job.get("location") or {}).get("name"),
        "requisition_id": job.get("requisition_id"),
        "first_published": job.get("first_published"),
        "updated_at": job.get("updated_at"),
        "employment_type": meta.get("Employment_Type"),
        "job_category": meta.get("커리어 페이지 노출 Job Category 값을 선택해주세요"),
        "keywords_external": meta.get("외부 노출용 키워드를 입력해주세요. (최대 4개  / 1번 키워드 = 포지션 카테고리 / 나머지 키워드 = 포지션 특성에 맞게 작성)"),
        "keywords_search": meta.get("검색에 쓰일 키워드를 입력해주세요(신규 비즈니스의 초기멤버라면, 초기멤버 키워드를 작성하세요)"),
        "description_markdown": jd,
        "raw": job,  # 원본까지 넣어두면 디버깅/확장에 좋음(용량은 좀 커짐)
    }

    rows.append({
        "title": job.get("title"),
        "company_name": company_name,
        "content_raw": json.dumps(content, ensure_ascii=False),
        "analysis_result": None,
        "original_url": job.get("absolute_url"),
    })

# ✅ on_conflict는 너가 unique 걸어둔 컬럼명과 같아야 함
res = sb.table("job_postings").upsert(rows, on_conflict="original_url").execute()
print("upsert rows:", len(rows))
