"""Research agent for the 100-app study.

Pipeline per app:
  1. Discover the search + scrape tool slugs inside a Composio session
     (COMPOSIO_SEARCH_TOOLS at runtime; no hardcoded slugs).
  2. Gather evidence from the public web with those Composio tools.
  3. Extract facts with Gemini (category, auth, access, API surface).
  4. Derive the buildability verdict LAST, from the extracted facts.

Usage:
  python src/research_agent.py --pilot     # one app per category (10)
  python src/research_agent.py --all       # all 100 (resumable)
  python src/research_agent.py --all --force   # ignore existing raw results
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# google-genai logs a one-time "direct use of AFC" warning for plain
# generate_content calls. It is harmless noise; keep stdout readable.
logging.getLogger("google_genai").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
APPS_CSV = ROOT / "apps.csv"
DATA_DIR = ROOT / "data"
RAW_PATH = DATA_DIR / "raw_results.json"

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
USER_ID = "research_agent"

# Evidence kept per app (chars). Enough for the model, small enough to stay cheap.
SEARCH_BLOB_LIMIT = 8000
PAGE_LIMIT = 6000
EVIDENCE_LIMIT = 18000

SLUG_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")
URL_RE = re.compile(r"https?://[^\s\"'<>\\]+")

EXTRACT_PROMPT = """You are a precise API research analyst. You will get evidence text gathered from the public web about one software product and must extract facts about its developer/API surface.

RULES:
- Use ONLY the evidence provided. Never invent facts.
- If something is not evidenced, use "unknown" (or [] / 0).
- Be specific and terse.
- Return ONLY a JSON object, no markdown fences, no commentary.

Required JSON shape:
{{
  "category": "one of: CRM and Sales | Support and Helpdesk | Communications and Messaging | Marketing, Ads, Email and Social | Ecommerce | Data, SEO and Scraping | Developer, Infra and Data platforms | Productivity and Project Management | Finance and Fintech | AI, Research and Media-native",
  "description": "one sentence on what the product does",
  "auth_methods": ["OAuth2", "API key", "Basic", "Bearer token", "other"...],
  "access": "self-serve | free-trial | paid-plan | admin-approval | partnership | contact-sales | unclear",
  "access_notes": "how a developer actually obtains credentials. A free developer edition, sandbox, or self-serve signup counts as self-serve/free-trial even if paid enterprise tiers also exist. Use paid-plan only when credentials need a paid subscription with no free/trial path.",
  "api_types": ["REST", "GraphQL", "webhook", "SDK", "none"...],
  "api_breadth": "broad | moderate | limited | none | unknown",
  "api_notes": "rough size/coverage of the public surface",
  "mcp": "official | community | none | unclear",
  "main_blocker": "the single biggest thing stopping an agent toolkit today, or none",
  "evidence_urls": ["2-5 documentation URLs you relied on; exclude images, favicons, CSS and nav assets"],
  "confidence": 0.0
}}

DO NOT output any buildability verdict. That is computed separately after these facts are known.

APP: {app}
KNOWN HINT: {hint}
CATEGORY GROUP (from the input list, verify against evidence): {group}

EVIDENCE:
{evidence}
"""


def to_obj(res: Any) -> Any:
    """Best-effort conversion of an SDK response to plain JSON data."""
    for attr in ("data", "result", "output"):
        if hasattr(res, attr):
            res = getattr(res, attr)
            break
    if hasattr(res, "model_dump"):
        try:
            return res.model_dump()
        except Exception:
            pass
    if isinstance(res, (dict, list)):
        return res
    try:
        return json.loads(res)
    except Exception:
        return {"raw": str(res)}


def dump(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return str(obj)


def collect_slugs(obj: Any, acc: set[str] | None = None) -> set[str]:
    """Recursively collect tool-slug-looking strings from a search response."""
    if acc is None:
        acc = set()
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key.lower() in ("primary_tool_slugs", "related_tool_slugs", "tools", "tool_slugs"):
                if isinstance(val, list):
                    for item in val:
                        if isinstance(item, str) and SLUG_RE.match(item):
                            acc.add(item)
                        elif isinstance(item, dict):
                            for k in ("tool_slug", "slug", "name"):
                                s = item.get(k)
                                if isinstance(s, str) and SLUG_RE.match(s):
                                    acc.add(s)
            if isinstance(val, str) and SLUG_RE.match(val) and key.lower() in ("tool_slug", "slug", "name"):
                acc.add(val)
            collect_slugs(val, acc)
    elif isinstance(obj, list):
        for item in obj:
            collect_slugs(item, acc)
    return acc


def extract_urls(obj: Any, limit: int = 25) -> list[str]:
    found: list[str] = []
    for m in URL_RE.finditer(dump(obj)):
        url = m.group(0).rstrip(").,;")
        if url not in found:
            found.append(url)
        if len(found) >= limit:
            break
    return found


class Researcher:
    def __init__(self) -> None:
        from composio import Composio
        from composio_gemini import GeminiProvider

        self.composio = Composio(provider=GeminiProvider())
        self.session = self.composio.create(user_id=USER_ID)
        self.search_slug = os.getenv("COMPOSIO_SEARCH_SLUG", "").strip()
        self.scrape_slug = os.getenv("COMPOSIO_SCRAPE_SLUG", "").strip()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client()
        return self._client

    SEARCH_USE_CASES = ["search the web with a text query and return links and snippets"]
    SCRAPE_USE_CASES = [
        "fetch and extract the readable text content of a single web page by its URL",
        "scrape a website URL and return its text",
    ]

    def _discover_slugs(self, use_cases: list[str]) -> set[str]:
        found: set[str] = set()
        for use_case in use_cases:
            try:
                res = self.session.execute(
                    "COMPOSIO_SEARCH_TOOLS",
                    arguments={"queries": [{"use_case": use_case}]},
                )
                found |= collect_slugs(to_obj(res))
            except Exception as exc:  # noqa: BLE001
                print(f"  [warn] discovery failed for '{use_case}': {exc}")
        return found

    @staticmethod
    def _pick_search(slugs: set[str]) -> str:
        skip = ("FETCH_URL", "URL_CONTENT", "GOOGLE_MAPS", "NEWS", "SCHOLAR", "BROWSER", "VERCEL")
        web = sorted(s for s in slugs if "SEARCH" in s and "WEB" in s and not any(t in s for t in skip))
        if web:
            return web[0]
        generic = sorted(s for s in slugs if "SEARCH" in s and not any(t in s for t in skip))
        return generic[0] if generic else ""

    @staticmethod
    def _pick_scrape(slugs: set[str]) -> str:
        for token in ("FETCH_URL_CONTENT", "SCRAPE_WEB_PAGE", "SCRAPE", "CRAWL"):
            hits = sorted(
                s for s in slugs if token in s and "BATCH" not in s and "ACCOUNT_INFO" not in s
            )
            if hits:
                return hits[0]
        return ""

    def discover(self) -> None:
        """Find search + scrape tool slugs at runtime via the session meta-tool."""
        if not self.search_slug:
            self.search_slug = self._pick_search(self._discover_slugs(self.SEARCH_USE_CASES))
        if not self.scrape_slug:
            self.scrape_slug = self._pick_scrape(self._discover_slugs(self.SCRAPE_USE_CASES))
        print(f"  discovered search={self.search_slug or '-'} scrape={self.scrape_slug or '-'}")
        if not self.search_slug:
            raise RuntimeError(
                "No search tool discovered. Set COMPOSIO_SEARCH_SLUG in .env to a Composio search tool slug."
            )

    def run_tool(self, slug: str, arguments: dict) -> Any:
        try:
            return to_obj(self.session.execute(slug, arguments=arguments))
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    def _try_args(self, slug: str, candidates: list[dict]) -> Any:
        last: Any = {}
        for args in candidates:
            res = self.run_tool(slug, args)
            if not (isinstance(res, dict) and res.get("error")):
                return res
            last = res
        return last

    def gather(self, app: str, hint: str) -> tuple[str, list[str]]:
        query = f"{app} API documentation authentication {hint}"
        res = self._try_args(
            self.search_slug,
            [{"query": query}, {"q": query}, {"search_query": query}],
        )
        blob = dump(res)
        urls = extract_urls(res)
        pages: list[str] = []
        if self.scrape_slug:
            ranked = sorted(urls, key=lambda u: (0 if ("docs" in u or "developer" in u or hint in u) else 1))
            for url in ranked[:2]:
                page = self._try_args(self.scrape_slug, [{"url": url}, {"urls": [url]}, {"link": url}])
                pages.append(f"SOURCE: {url}\n{dump(page)[:PAGE_LIMIT]}")
        evidence = f"SEARCH RESULTS:\n{blob[:SEARCH_BLOB_LIMIT]}\n\nSCRAPED PAGES:\n" + "\n\n".join(pages)
        return evidence[:EVIDENCE_LIMIT], urls[:8]

    def model_chain(self) -> list[str]:
        extra = os.getenv(
            "GEMINI_FALLBACK_MODELS",
            "gemini-3.5-flash,gemini-3.6-flash,gemini-3.1-flash-lite",
        )
        chain: list[str] = []
        for m in [MODEL, *extra.split(",")]:
            m = m.strip()
            if m and m not in chain:
                chain.append(m)
        return chain

    def extract(self, app: str, hint: str, group: str, evidence: str) -> dict:
        from google.genai import types

        prompt = EXTRACT_PROMPT.format(app=app, hint=hint, group=group, evidence=evidence)
        last_exc: Exception | None = None
        for model in self.model_chain():
            for attempt in range(3):
                try:
                    resp = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            temperature=0, response_mime_type="application/json"
                        ),
                    )
                    data = parse_json(resp.text)
                    data["_model"] = model
                    return data
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    wait = 3 * (attempt + 1)
                    print(f"  [warn] {model} attempt {attempt + 1} failed in {wait}s: {str(exc)[:70]}")
                    time.sleep(wait)
            print(f"  [warn] moving off {model} (3 failed attempts)")
        return {"error": f"extraction failed: {last_exc}"}


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"error": "unparseable model output", "raw": text[:500]}


def as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip() and value.lower() != "unknown":
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def derive_buildability(facts: dict) -> tuple[str, str, str]:
    """Buildability verdict, produced LAST from the already-extracted facts."""
    access = str(facts.get("access", "unclear")).lower()
    breadth = str(facts.get("api_breadth", "unknown")).lower()
    api_types = [t.lower() for t in as_list(facts.get("api_types"))]
    has_api = breadth in ("broad", "moderate", "limited") and bool(api_types) and "none" not in api_types
    blocker = str(facts.get("main_blocker", "") or "").strip()
    if blocker.lower() in ("none", "n/a"):
        blocker = ""
    notes = str(facts.get("access_notes", "") or "").strip()

    if not has_api:
        return "no", "No documented public API", "API surface is missing or undocumented."
    if access in ("partnership", "contact-sales", "admin-approval"):
        return "no", blocker or notes or "Credentials require approval or a partnership", f"Access is {access}."
    if access == "self-serve":
        return "yes", blocker, "Self-serve credentials and a public API."
    if access in ("free-trial", "paid-plan"):
        return "partial", blocker or notes, f"Credentials need a {access}; API itself is documented."
    return "partial", blocker or notes or "Access path is unclear", f"Access classified as {access}."


def load_apps() -> list[dict]:
    with APPS_CSV.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def select(apps: list[dict], pilot: bool) -> list[dict]:
    if not pilot:
        return apps
    seen: set[str] = set()
    picked: list[dict] = []
    for app in apps:
        if app["category"] not in seen:
            seen.add(app["category"])
            picked.append(app)
    return picked


def load_raw() -> dict:
    if RAW_PATH.exists():
        return json.loads(RAW_PATH.read_text(encoding="utf-8-sig"))
    return {}


def save_raw(raw: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true", help="one app per category")
    ap.add_argument("--all", action="store_true", help="all apps")
    ap.add_argument("--limit", type=int, default=0, help="cap to the first N apps (smoke test)")
    ap.add_argument("--force", action="store_true", help="redo apps already researched")
    args = ap.parse_args()
    if not (args.pilot or args.all):
        ap.error("pass --pilot or --all")

    apps = select(load_apps(), pilot=args.pilot)
    if args.limit:
        apps = apps[: args.limit]
    raw = load_raw()

    researcher = Researcher()
    researcher.discover()

    for i, app in enumerate(apps, 1):
        key = str(app["id"])
        if key in raw and not args.force:
            print(f"[{i}/{len(apps)}] skip {app['app']} (cached)")
            continue
        print(f"[{i}/{len(apps)}] {app['app']}")
        evidence, urls = researcher.gather(app["app"], app["hint"])
        facts = researcher.extract(app["app"], app["hint"], app["category"], evidence)
        if "error" in facts:
            print(f"  [error] {facts['error']}")
            raw[key] = {"id": app["id"], "app": app["app"], "hint": app["hint"], "error": facts["error"]}
            save_raw(raw)
            continue
        facts.setdefault("evidence_urls", [])
        for url in urls:
            if url not in facts["evidence_urls"]:
                facts["evidence_urls"].append(url)

        # Verdict LAST — after category, auth, access and API surface are known.
        verdict, blocker, reason = derive_buildability(facts)

        raw[key] = {
            "id": int(app["id"]),
            "app": app["app"],
            "hint": app["hint"],
            "category_graph": app["category"],
            "category": facts.get("category", "unknown"),
            "description": facts.get("description", ""),
            "auth_methods": as_list(facts.get("auth_methods")),
            "access": facts.get("access", "unclear"),
            "access_notes": facts.get("access_notes", ""),
            "api_types": as_list(facts.get("api_types")),
            "api_breadth": facts.get("api_breadth", "unknown"),
            "api_notes": facts.get("api_notes", ""),
            "mcp": facts.get("mcp", "unclear"),
            "buildability": verdict,
            "main_blocker": blocker,
            "buildability_reason": reason,
            "evidence_urls": facts.get("evidence_urls", []),
            "confidence": facts.get("confidence", 0),
            "model_used": facts.get("_model", ""),
            "researched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        save_raw(raw)
        print(f"  -> {verdict} | {', '.join(raw[key]['auth_methods']) or 'auth?'} | {raw[key]['access']}")

    print(f"\nSaved {len(raw)} results to {RAW_PATH}")


if __name__ == "__main__":
    main()
