"""DSPy tools on Datacircle's open API, https://api.datacircle.dev/v1: no key, no account."""

import urllib.parse
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional

import dspy

from dspy_datacircle import _api

SORTS = ("score", "provider", "price")
NAMES = ("list_apis", "best_plans", "search_plans", "provider")


def _number(value: Any, name: str, low: int, high: Optional[int]) -> Optional[int]:
    """A model's limit or offset as a whole number in its range, or None when left out."""
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise _api.DatacircleError(f"{name} must be a whole number, not {value!r}") from None
    if number != value and str(number) != str(value).strip():
        raise _api.DatacircleError(f"{name} must be a whole number, not {value!r}")
    if number < low or (high is not None and number > high):
        raise _api.DatacircleError(f"{name} must be {low} or more" + (f" and {high} or less" if high is not None else ""))
    return number


def _answer(make: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    """What the API gave, or {"error": ...} with its words for the model to read."""
    try:
        return make()
    except _api.DatacircleError as error:
        return {"error": str(error)}


def _best(plans: Any) -> Optional[Dict[str, Any]]:
    """A provider's best plan on an API: its lowest rank, a plan with no score having none."""
    ranked = sorted(plans, key=lambda plan: plan.get("rank") if isinstance(plan.get("rank"), (int, float)) else float("inf"))
    return _api.brief(ranked[0], ["plan", "score", "perThousand", "page"]) if ranked else None


class Datacircle:
    """Datacircle's benchmark of GTM APIs (https://datacircle.dev): every API it lists, who is best for each, every plan
    and each provider's ranks, from its open API. Each method makes one HTTPS GET and gives the answer as a dict, or
    {"error": ...} with the API's words.

    Args:
        base_url: The API's address. Default https://api.datacircle.dev/v1.
        timeout: Seconds each HTTP request may take. Default 30.
    """

    def __init__(self, base_url: str = _api.BASE_URL, timeout: float = 30):
        self.base_url = base_url
        self.timeout = timeout

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return _api.get(path, params, base_url=self.base_url, timeout=self.timeout)

    def list_apis(self, query: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Lists the GTM APIs on Datacircle's sheet, each with its slug, how many plans and providers it has and its
        best plan: the ones whose name holds the most of query's words first. Gives total and up to limit (20) APIs."""

        def make() -> Dict[str, Any]:
            most = _number(limit, "limit", 1, 200) or 20
            apis = self._get("/apis")
            words = [word for word in str(query or "").lower().replace("-", " ").split() if word]
            held = []
            for index, api in enumerate(apis):
                name = f"{api.get('api', '')} {str(api.get('slug', '')).replace('-', ' ')}".lower()
                matched = sum(word in name for word in words)
                if matched or not words:
                    held.append((-matched, index, api))
            found = [_api.brief(api, _api.API_KEYS) for _, _, api in sorted(held, key=lambda h: h[:2])]
            return {"total": len(found), "apis": found[:most]}

        return _answer(make)

    def best_plans(self, slug: str, limit: Optional[int] = None) -> Dict[str, Any]:
        """Gives an API's plans best first by their score out of 100, each with its rank, provider, plan, $ per 1,000
        calls and its page: slug is the API's slug or name, limit 1 to 50 (10)."""

        def make() -> Dict[str, Any]:
            made = _api.slug(slug)
            if not made:
                raise _api.DatacircleError("Give an API's slug, like 'email-finder': datacircle_list_apis gives every slug")
            answer = self._get(f"/apis/{urllib.parse.quote(made)}/best", {"limit": _number(limit, "limit", 1, 50)})
            return {**answer, "plans": [_api.brief(plan) for plan in answer.get("plans") or []]}

        return _answer(make)

    def search_plans(
        self,
        api: Optional[str] = None,
        query: Optional[str] = None,
        sort: Optional[Literal["score", "provider", "price"]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Searches every plan, or one API's, by provider or plan name, sorted by score (the default), provider or
        price. Gives total, offset and up to limit (10) plans."""

        def make() -> Dict[str, Any]:
            order = str(sort).strip().lower() if sort not in (None, "") else None
            if order is not None and order not in SORTS:
                raise _api.DatacircleError(f"sort must be score, provider or price, not {sort!r}")
            params = {"api": api, "query": query, "sort": order, "limit": _number(limit, "limit", 1, 50),
                      "offset": _number(offset, "offset", 0, None)}
            answer = self._get("/plans", params)
            return {**answer, "plans": [_api.brief(plan) for plan in answer.get("plans") or []]}

        return _answer(make)

    def provider(self, slug: str) -> Dict[str, Any]:
        """Gives each API one provider sells and its rank on each, with its best plan there: slug is the provider's
        slug or name."""

        def make() -> Dict[str, Any]:
            made = _api.slug(slug)
            if not made:
                raise _api.DatacircleError("Give a provider's slug or name, like 'bright-data' or 'Bright Data'")
            answer = self._get(f"/providers/{urllib.parse.quote(made)}")
            apis = [{**_api.brief(entry, ["api", "slug", "rank", "bestPage"]), "plans": len(entry.get("plans") or []),
                     "best": _best(entry.get("plans") or [])} for entry in answer.get("apis") or []]
            return {**answer, "apis": apis}

        return _answer(make)

    def tools(self, include: Optional[Iterable[str]] = None) -> List[dspy.Tool]:
        """The methods as dspy.Tool, named datacircle_<method>, with what a model reads of each: all four, or those
        include names (list_apis, best_plans, search_plans, provider)."""
        names = list(NAMES) if include is None else [str(name).removeprefix("datacircle_") for name in include]
        unknown = [name for name in names if name not in NAMES]
        if unknown:
            raise ValueError(f"No such Datacircle tool: {', '.join(unknown)}. The tools: {', '.join(NAMES)}")
        return [dspy.Tool(getattr(self, name), name=f"datacircle_{name}", desc=DESCRIPTIONS[name],
                          arg_desc=ARGUMENTS[name]) for name in NAMES if name in names]


PER_THOUSAND = ("perThousand is a plan's price of 1,000 items in dollars, pay the plan's whole price in its currency.")

DESCRIPTIONS = {
    "list_apis": "Lists the GTM APIs on Datacircle's sheet (https://datacircle.dev), with each API's slug, how many "
                 "plans and providers it has and its best plan. Call it first to find an API's slug. Gives total, the "
                 "APIs found, and apis, up to limit of them.",
    "best_plans": "Gives an API's plans best first by their score out of 100 on Datacircle's benchmark "
                  "(https://datacircle.dev), each with its rank, provider, plan, $ per 1,000 calls and its page. "
                  + PER_THOUSAND,
    "search_plans": "Searches every plan on Datacircle's sheet (https://datacircle.dev), or one API's, by provider or "
                    "plan name, sorted by score, provider or price. Gives total, offset and up to limit plans. "
                    + PER_THOUSAND,
    "provider": "Gives each API one provider sells and its rank on each on Datacircle's benchmark "
                "(https://datacircle.dev), with its best plan there.",
}

ARGUMENTS = {
    "list_apis": {
        "query": "Words of the API's name or slug, like 'email' or 'linkedin profile': the APIs that hold the most of "
                 "them come first. The sheet's order when left out.",
        "limit": "How many APIs to give, 1 to 200. 20 when left out: the sheet has about 150.",
    },
    "best_plans": {
        "slug": "The API's slug, like 'email-finder' or 'linkedin-profile', as datacircle_list_apis gives it.",
        "limit": "How many plans to give, 1 to 50. 10 when left out.",
    },
    "search_plans": {
        "api": "Only this API's plans: its name or slug, like 'email-finder'. A provider's name goes in query, never "
               "here. Every API when left out.",
        "query": "Words that must all appear in the provider's or plan's name, like 'bright data'.",
        "sort": "score (best first, the default), provider (A to Z) or price ($ per 1,000, lowest first).",
        "limit": "How many plans to give, 1 to 50. 10 when left out.",
        "offset": "How many found plans to skip first. 0 when left out.",
    },
    "provider": {
        "slug": "The provider's slug, like 'bright-data', or its name, like 'Bright Data': the name is made a slug.",
    },
}

_default = Datacircle()
list_apis = _default.list_apis
best_plans = _default.best_plans
search_plans = _default.search_plans
provider = _default.provider


def datacircle_tools(include: Optional[Iterable[str]] = None, base_url: str = _api.BASE_URL,
                     timeout: float = 30) -> List[dspy.Tool]:
    """Datacircle's four tools as dspy.Tool, for dspy.ReAct(signature, tools=datacircle_tools()): datacircle_list_apis,
    datacircle_best_plans, datacircle_search_plans and datacircle_provider, or those include names."""
    return Datacircle(base_url, timeout).tools(include)
