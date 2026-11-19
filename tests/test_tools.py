"""The tools with no network: what each sends to the API, what a model reads of each, and how answers and refusals reach it."""

import json

import dspy
import pytest
import requests

from dspy_datacircle import Datacircle, _api, best_plans, datacircle_tools, list_apis, provider, search_plans

NAMES = ["datacircle_list_apis", "datacircle_best_plans", "datacircle_search_plans", "datacircle_provider"]


@pytest.fixture
def api(monkeypatch):
    """requests.get answering from a dict of path to (status, body), each request kept."""
    sent, answers = [], {}

    def get(url, params=None, headers=None, timeout=None, allow_redirects=None):
        sent.append((url, dict(params or {})))
        status, body = answers[url.split("/v1", 1)[1]]
        answer = requests.Response()
        answer.status_code, answer._content = status, json.dumps(body).encode()
        answer.headers["Retry-After"] = "1"
        return answer

    monkeypatch.setattr(_api.requests, "get", get)
    monkeypatch.setattr(_api.time, "sleep", lambda seconds: None)
    return sent, answers


def test_the_four_tools_as_a_model_reads_them():
    tools = datacircle_tools()
    assert [tool.name for tool in tools] == NAMES
    assert all(isinstance(tool, dspy.Tool) and "https://datacircle.dev" in tool.desc for tool in tools)
    assert list(tools[2].args) == ["api", "query", "sort", "limit", "offset"]
    assert "lowest first" in tools[2].args["sort"]["description"]
    assert [tool.name for tool in datacircle_tools(include=["provider", "datacircle_best_plans"])] == NAMES[1:4:2]
    with pytest.raises(ValueError, match="list_apis, best_plans"):
        datacircle_tools(include=["plans"])


def test_list_apis_puts_the_best_match_first(api):
    sent, answers = api
    answers["/apis"] = (200, [{"api": "Employee profile", "slug": "linkedin-profile", "plans": 9},
                              {"api": "Employee email", "slug": "email-finder", "plans": 5, "extra": "cut"},
                              {"api": "Email verification", "slug": "email-verification", "plans": 3}])
    assert list_apis(query="email finder", limit=1) == {"total": 2, "apis": [{"api": "Employee email", "slug": "email-finder", "plans": 5}]}
    assert list_apis()["total"] == 3


def test_best_plans_makes_a_slug_and_keeps_the_keys_that_choose_a_plan(api):
    sent, answers = api
    answers["/apis/email-finder/best"] = (200, {"api": "Employee email", "total": 1, "plans": [
        {"rank": 1, "provider": "Emelia", "perThousand": 4.99, "aggregators": ["x"], "latencyMs": None}]})
    out = datacircle_tools()[1](slug="Email Finder", limit="3")
    assert sent == [("https://api.datacircle.dev/v1/apis/email-finder/best", {"limit": 3})]
    assert out["plans"] == [{"rank": 1, "provider": "Emelia", "perThousand": 4.99}]


def test_search_plans_sends_only_what_is_given(api):
    sent, answers = api
    answers["/plans"] = (200, {"total": 0, "offset": 5, "plans": []})
    search_plans(query="hunter", sort="Price", offset=5)
    assert sent[-1][1] == {"query": "hunter", "sort": "price", "offset": 5}
    assert "sort must be" in search_plans(sort="cheapest")["error"]


def test_provider_gives_its_best_plan_on_each_api(api):
    sent, answers = api
    answers["/providers/bright-data"] = (200, {"provider": "Bright Data", "apis": [{"api": "Employee profile", "slug": "linkedin-profile",
        "rank": 2, "plans": [{"plan": "B", "rank": 5, "score": 70}, {"plan": "A", "rank": 2, "score": 90, "perThousand": 1.5}]}]})
    out = provider(slug="Bright Data")
    assert out["apis"] == [{"api": "Employee profile", "slug": "linkedin-profile", "rank": 2, "plans": 2,
                            "best": {"plan": "A", "score": 90, "perThousand": 1.5}}]


def test_refusals_reach_the_model_in_the_apis_words(api):
    sent, answers = api
    answers["/apis/nope/best"] = (404, {"error": "No API nope", "slugs": ["email-finder", "linkedin-profile"]})
    assert best_plans(slug="nope") == {"error": "Datacircle's API answered 404: No API nope; the slugs: email-finder, linkedin-profile"}
    assert "limit must be 1 or more" in best_plans(slug="email-finder", limit=0)["error"]
    assert "whole number" in best_plans(slug="email-finder", limit=2.5)["error"]
    assert "Give a provider" in provider(slug="  ")["error"]
    answers["/apis"] = (429, {"error": "slow down"})
    assert "429 twice" in list_apis()["error"]
    assert len(sent) == 3


def test_another_address(api):
    sent, answers = api
    answers["/apis"] = (200, [])
    Datacircle(base_url="https://example.test/v1/").list_apis()
    datacircle_tools(base_url="https://example.test/v1")[0]()
    assert [url for url, _ in sent] == ["https://example.test/v1/apis"] * 2
