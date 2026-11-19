"""One HTTPS GET to Datacircle's open API (https://api.datacircle.dev/v1), no key, and what its answers are cut to for a model."""

import re
import time
import unicodedata
from typing import Any, Dict, List, Optional

import requests

BASE_URL = "https://api.datacircle.dev/v1"
USER_AGENT = "dspy-datacircle/0.1.0"

# A plan holds about 90 keys (its terms of use, its aggregators...): the tools keep the ones that choose a plan, the rest is on its page.
PLAN_KEYS = ["api", "rank", "provider", "plan", "score", "perThousand", "notFoundPerThousand", "billing", "pay",
             "currency", "units", "unit", "strengths", "latencyMs", "page", "pricingPage", "docs"]
API_KEYS = ["api", "slug", "plans", "providers", "best", "bestPage", "sheetPage"]


class DatacircleError(Exception):
    """The API's refusal in its own words, or why it could not be reached: a tool gives it to the model as its answer."""


def brief(item: Dict[str, Any], keys: List[str] = PLAN_KEYS) -> Dict[str, Any]:
    return {key: item[key] for key in keys if item.get(key) is not None}


def slug(value: Any) -> str:
    """The API's rule for a slug: the name in lowercase letters and digits, the rest a hyphen."""
    plain = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def get(path: str, params: Optional[Dict[str, Any]] = None, base_url: str = BASE_URL, timeout: float = 30) -> Any:
    """The API's JSON answer, or a DatacircleError with its words: an unknown slug's answer lists every slug."""
    query = {key: value for key, value in (params or {}).items() if value not in (None, "")}
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    for attempt in range(2):
        try:
            answer = requests.get(url, params=query, headers=headers, timeout=timeout, allow_redirects=True)
        except requests.RequestException as error:
            raise DatacircleError(f"Datacircle's API could not be reached: {error}") from None
        if answer.status_code == 429:
            if attempt:
                break
            try:
                wait = int(answer.headers.get("Retry-After") or 30)
            except ValueError:
                wait = 30
            time.sleep(min(max(wait, 1), 60))
            continue
        if answer.status_code >= 400:
            words = answer.text
            try:
                parsed = answer.json()
                words = f"{parsed['error']}; the slugs: {', '.join(parsed['slugs'])}" if parsed.get("slugs") else parsed.get("error", words)
            except (ValueError, KeyError, TypeError, AttributeError):
                pass
            raise DatacircleError(f"Datacircle's API answered {answer.status_code}: {str(words)[:3000]}")
        try:
            return answer.json()
        except ValueError as error:
            raise DatacircleError(f"Datacircle's API gave no JSON: {error}") from None
    raise DatacircleError("Datacircle's API answered 429 twice: wait a minute and call again")
