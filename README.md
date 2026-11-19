# dspy-datacircle

Find the best GTM APIs. We benchmark all the GTM APIs and we put the results on our website: https://datacircle.dev

This package gives DSPy four tools on Datacircle's open API, https://api.datacircle.dev/v1. You need no key and no account.

```bash
pip install dspy-datacircle
```

| Tool | What it gives | Call |
| --- | --- | --- |
| `datacircle_list_apis` | Every GTM API on Datacircle, with its slug, number of plans and providers, and its best plan | `GET /apis` |
| `datacircle_best_plans` | One API's plans, best first by score out of 100, each with its rank and price per 1,000 calls | `GET /apis/{slug}/best` |
| `datacircle_search_plans` | Plans by provider or plan name, on every API or one, sorted by score, provider or price | `GET /plans` |
| `datacircle_provider` | The APIs a provider sells and its rank on each | `GET /providers/{slug}` |

## Use

```python
import dspy
from dspy_datacircle import datacircle_tools

dspy.configure(lm=dspy.LM("openai/gpt-4o-mini"))
agent = dspy.ReAct("question -> answer", tools=datacircle_tools())
print(agent(question="Which email finder API is best for under $5 per 1,000?").answer)
```

Any DSPy model works. `datacircle_tools(include=["best_plans", "provider"])` gives only some of the tools. `dspy.RLM` takes the same tools: the code it writes calls them by name.

Each tool is also a plain function that gives a dict:

```python
from dspy_datacircle import best_plans

best_plans(slug="email-finder", limit=3)
```

An unknown slug or a value out of range comes back as `{"error": ...}` with the API's words (an unknown API's answer lists every slug).

## Network

Each call makes one HTTPS GET to https://api.datacircle.dev/v1 with the tool's arguments and nothing else. The API takes up to 60 calls a minute from one address; the tools wait once, a minute at most, when it asks them to. Every plan is also one file at https://datacircle.dev/datacircle.json.

## Links

- Datacircle: https://datacircle.dev
- The API: https://datacircle.dev/api
- Its spec: https://api.datacircle.dev/v1/openapi.json
- What each key means: https://datacircle.dev/fields

MIT license.
