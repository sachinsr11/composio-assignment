"""Cluster the research results into patterns -> data/insights.json.

Usage: python src/analyze.py
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_PATH = DATA_DIR / "raw_results.json"
INSIGHTS_PATH = DATA_DIR / "insights.json"

GATE = {"partnership", "contact-sales", "admin-approval"}
ACCESS_ORDER = [
    "self-serve",
    "free-trial",
    "paid-plan",
    "admin-approval",
    "partnership",
    "contact-sales",
    "unclear",
]


def norm_auth(method: str) -> str:
    m = method.lower()
    if "oauth" in m:
        return "OAuth2"
    if "api key" in m or "apikey" in m or "api-key" in m:
        return "API key"
    if "basic" in m:
        return "Basic"
    if "bearer" in m or "token" in m:
        return "Token"
    if "jwt" in m:
        return "JWT"
    return method.strip() or "Unknown"


def blocker_bucket(text: str) -> str | None:
    """Turn one-off blocker sentences into a small set of meaningful categories."""
    if not text:
        return None
    t = text.lower()
    if "no documented public api" in t or "no public api" in t or "not documented" in t:
        return "No public API"
    if "approval" in t or "app review" in t or "manual review" in t:
        return "Requires approval"
    if "partner" in t or "contact sales" in t or "contact-sales" in t:
        return "Partnership / contact sales"
    if "rate limit" in t or "quota" in t or "throttl" in t:
        return "Rate limits / quota"
    if (
        "paid" in t
        or "subscription" in t
        or "licens" in t
        or "pricing" in t
        or "billing" in t
        or "cost" in t
    ):
        return "Paid plan required"
    if (
        "enterprise" in t
        or "multi-step" in t
        or "slas" in t
        or "account manager" in t
        or "complex" in t
    ):
        return "Complex enterprise setup"
    return "Other"


def main() -> None:
    rows = json.loads(RAW_PATH.read_text(encoding="utf-8-sig"))
    rows = [r for r in rows.values() if "error" not in r]

    auth = Counter()
    access = Counter()
    build = Counter()
    mcp = Counter()
    blockers = Counter()
    cat_access: dict[str, Counter] = defaultdict(Counter)

    oauth_apps = 0
    for row in rows:
        methods = {norm_auth(m) for m in (row.get("auth_methods") or ["Unknown"])}
        for method in methods:
            auth[method] += 1
        if "OAuth2" in methods:
            oauth_apps += 1
        access[row.get("access", "unclear")] += 1
        build[row.get("buildability", "unknown")] += 1

        # MCP: this research pass did not target MCP, so a bare "none" is not an
        # assessment. Report it as "not assessed" rather than asserting absence.
        raw_mcp = row.get("mcp", "unclear")
        mcp["not assessed" if raw_mcp in ("none", "unclear", "") else raw_mcp] += 1

        bucket = blocker_bucket(row.get("main_blocker", ""))
        if bucket:
            blockers[bucket] += 1
        cat_access[row.get("category_graph", row.get("category", "?"))][
            row.get("access", "unclear")
        ] += 1

    easy = [r["app"] for r in rows if r.get("buildability") == "yes"]
    outreach = [r["app"] for r in rows if r.get("buildability") == "no" and r.get("access") in GATE]
    no_api = [r["app"] for r in rows if r.get("buildability") == "no" and r.get("access") not in GATE]

    total = len(rows)
    insights = {
        "total": total,
        "auth": dict(auth.most_common()),
        "access": dict(access.most_common()),
        "buildability": dict(build.most_common()),
        "mcp": dict(mcp.most_common()),
        "top_blockers": dict(blockers.most_common()),
        "category_access": {k: dict(v) for k, v in sorted(cat_access.items())},
        "access_order": ACCESS_ORDER,
        "easy_wins": easy,
        "needs_outreach": outreach,
        "no_public_api": no_api,
        "self_serve_share": round(access.get("self-serve", 0) / total, 3) if total else 0,
        "buildable_share": round(build.get("yes", 0) / total, 3) if total else 0,
        "oauth_apps": oauth_apps,
        "oauth_share": round(oauth_apps / total, 3) if total else 0,
    }
    DATA_DIR.mkdir(exist_ok=True)
    INSIGHTS_PATH.write_text(json.dumps(insights, indent=2), encoding="utf-8")

    print(f"Apps analysed: {insights['total']}")
    print(f"Auth (apps per method): {insights['auth']}")
    print(f"Access: {insights['access']}")
    print(f"Buildability: {insights['buildability']}")
    print(f"Self-serve share: {insights['self_serve_share']} | OAuth2 apps: {oauth_apps} ({insights['oauth_share']})")
    print(f"Easy wins: {len(easy)} | Needs outreach: {len(outreach)} | No public API: {len(no_api)}")
    print(f"Top blockers: {insights['top_blockers']}")
    print(f"MCP: {insights['mcp']}")
    print(f"-> {INSIGHTS_PATH}")


if __name__ == "__main__":
    main()
