# JD Crawler

Supabase 기반 채용공고 크롤러. GitHub Actions로 매일 자동 실행.

## 로컬 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
```

`.env` 파일:
```
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SECRET_KEY=sb_secret_xxxxxxxxxxxxxxxx
```

> **키 발급 위치**: Supabase Dashboard > Project Settings > API > **Secret keys** (`sb_secret_...`)
>
> Legacy `service_role` 키도 fallback으로 지원됨 (`SUPABASE_SERVICE_ROLE_KEY`)

```bash
# 실행
python -m src.main
```

## Supabase 설정

### 테이블 스키마

```sql
-- crawl_targets
CREATE TABLE crawl_targets (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  list_url TEXT NOT NULL,
  parser_type TEXT DEFAULT 'generic',
  parser_config JSONB,
  is_active BOOLEAN DEFAULT true,
  last_list_hash TEXT,
  last_checked_at TIMESTAMPTZ
);

-- job_postings
CREATE TABLE job_postings (
  id SERIAL PRIMARY KEY,
  crawl_target_id INTEGER REFERENCES crawl_targets(id),
  title TEXT NOT NULL,
  company_name TEXT,
  content_raw TEXT,
  original_url TEXT UNIQUE NOT NULL,
  analysis_result JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Target 추가 예시

```sql
INSERT INTO crawl_targets (name, list_url, parser_type, parser_config, is_active)
VALUES (
  '예시 채용사이트',
  'https://example.com/jobs',
  'generic',
  '{
    "list_selector": ".job-list .job-item",
    "title_selector": ".job-title",
    "link_selector": "a",
    "company_selector": ".company-name",
    "detail_selector": ".job-description",
    "base_url": "https://example.com"
  }',
  true
);
```

## GitHub Actions 설정

Repository > Settings > Secrets and variables > Actions > New repository secret

| Name | Value |
|------|-------|
| `SUPABASE_URL` | `https://xxxxx.supabase.co` |
| `SUPABASE_SECRET_KEY` | `sb_secret_xxxxxxxxxxxxxxxx` |

> **키 발급**: Supabase Dashboard > Project Settings > API > **Secret keys**

실행 스케줄: 매일 KST 06:00 (UTC 21:00)

수동 실행: Actions 탭 > Daily Job Crawl > Run workflow

## 주의사항

### UTC Cron
GitHub Actions cron은 **UTC 기준**. KST로 변환 필요:
- KST 06:00 = UTC 21:00 (전날)
- `cron: '0 21 * * *'`

### Public Repo 60일 비활성화
Public repository에서 60일간 커밋이 없으면 scheduled workflow가 **자동 비활성화**됨.
- 해결: 주기적으로 커밋하거나, Actions 탭에서 수동으로 re-enable

### Secret Key 보안

`SUPABASE_SECRET_KEY` (`sb_secret_...`)는 **RLS를 우회**하는 서버 전용 키.

- **절대 클라이언트/프론트엔드 코드에 넣지 말 것**
- **절대 코드에 하드코딩하지 말 것**
- **절대 로그에 출력하지 말 것**
- Public repo라면 **반드시 GitHub Secrets로만 관리**
- 로컬 `.env`는 `.gitignore`에 추가

```gitignore
.env
```

> Legacy `service_role` 키를 사용 중이라면 `SUPABASE_SERVICE_ROLE_KEY`로도 동작하지만,
> 새 프로젝트는 `SUPABASE_SECRET_KEY` 사용을 권장.

## 파서 확장

`src/parsers/`에 새 파서 추가:

```python
# src/parsers/wanted.py
from src.parsers.base import BaseParser, JobItem

class WantedParser(BaseParser):
    def parse_list(self, html: str) -> list[JobItem]:
        # 구현
        ...

    def parse_detail(self, html: str) -> str:
        # 구현
        ...
```

`src/parsers/__init__.py`에 등록:
```python
from src.parsers.wanted import WantedParser
PARSER_REGISTRY["wanted"] = WantedParser
```

## Toss API 파서

Toss 채용공고는 API 기반 파서(`toss_job_groups_api`)를 사용.

### Target 추가

```sql
-- crawl_targets에 last_error 컬럼이 없으면 추가
ALTER TABLE crawl_targets ADD COLUMN IF NOT EXISTS last_error TEXT;

-- Toss target 추가
INSERT INTO crawl_targets (name, list_url, parser_type, is_active)
VALUES (
  'Toss Jobs',
  'https://api-public.toss.im/api/v3/ipd-eggnog/career/job-groups',
  'toss_job_groups_api',
  true
);
```

### 로컬 테스트 순서

```bash
# 1) API fetch 테스트 (DB 없이)
python scripts/test_toss_fetch.py

# 2) Supabase upsert 테스트
python scripts/test_toss_upsert.py

# 3) 메인 크롤러로 실행 (변경 감지 포함)
python -m src.main

# 4) 바로 다시 실행하면 SKIP 확인
python -m src.main
# → "[SKIP] No changes detected for Toss Jobs (unchanged)"
```

### 변경 감지 동작

- API 응답에서 `(job.id, job.updated_at)` 쌍을 정렬 후 SHA256 해시 생성
- `crawl_targets.last_list_hash`와 비교
- 같으면: upsert 스킵, `last_checked_at`만 업데이트
- 다르면: upsert 수행 후 `last_list_hash`, `last_checked_at` 업데이트, `last_error` = null
- 실패 시: `last_error`에 에러 메시지 저장

### DB 제약 조건 확인

`job_postings.original_url`에 UNIQUE 제약이 필수. 없으면 upsert 실패:

```
ERROR: there is no unique or exclusion constraint matching the ON CONFLICT specification
```

수정 SQL:
```sql
-- UNIQUE 제약 추가
ALTER TABLE job_postings
ADD CONSTRAINT job_postings_original_url_key UNIQUE (original_url);

-- 확인
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_name = 'job_postings' AND constraint_type = 'UNIQUE';
```
