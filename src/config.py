import os
import sys
from dotenv import load_dotenv

load_dotenv()


def _get_secret_key() -> str:
    """
    Get Supabase secret key with fallback support.
    Priority: SUPABASE_SECRET_KEY > SUPABASE_SERVICE_ROLE_KEY (legacy)
    """
    key = os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        print(
            "[FATAL] Missing Supabase secret key.\n"
            "Set one of the following environment variables:\n"
            "  - SUPABASE_SECRET_KEY (recommended, sb_secret_...)\n"
            "  - SUPABASE_SERVICE_ROLE_KEY (legacy)\n\n"
            "Get your secret key from:\n"
            "  Supabase Dashboard > Project Settings > API > Secret keys"
        )
        sys.exit(1)
    return key


def _get_url() -> str:
    """Get Supabase URL."""
    url = os.environ.get("SUPABASE_URL")
    if not url:
        print(
            "[FATAL] Missing SUPABASE_URL environment variable.\n"
            "Get your project URL from:\n"
            "  Supabase Dashboard > Project Settings > API > Project URL"
        )
        sys.exit(1)
    return url


SUPABASE_URL = _get_url()
SUPABASE_SECRET_KEY = _get_secret_key()

# Crawler settings
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# User-Agent for requests
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
