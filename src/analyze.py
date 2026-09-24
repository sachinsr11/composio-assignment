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


def main() -> None:
    rows = json.loads(RAW_PATH.read_text(encoding="utf-8-sig"))
    rows = [r for r in rows.values() if "error" not in r]

    auth = Counter()
    access = Counter()
    build = Counter()
    mcp = Counter()
    blockers = Counter()
    cat_access: dict[str, Counter] = defaultdict(Counter)

    for row in rows:
        for method in row.get("auth_methods") or ["Unknown"]:
            auth[norm_auth(method)] += 1
        access[row.get("access", "unclear")] += 1
        build[row.get("buildability", "unknown")] += 1
        mcp[row.get("mcp", "unclear")] += 1
        if row.get("main_blocker"):
            blockers[row["main_blocker"]] += 1
        cat_access[row.get("category_graph", row.get("category", "?"))][row.get("access", "unclear")] += 1

    easy = [r["app"] for r in rows if r.get("buildability") == "yes"]
    outreach = [r["app"] for r in rows if r.get("buildability") == "no" and r.get("access") in GATE]
    no_api = [r["app"] for r in rows if r.get("buildability") == "no" and r.get("access") not in GATE]

    insights = {
        "total": len(rows),
        "auth": dict(auth.most_common()),
        "access": dict(access.most_common()),
        "buildability": dict(build.most_common()),
        "mcp": dict(mcp.most_common()),
        "top_blockers": dict(blockers.most_common(10)),
        "category_access": {k: dict(v) for k, v in sorted(cat_access.items())},
        "easy_wins": easy,
        "needs_outreach": outreach,
        "no_public_api": no_api,
        "self_serve_share": round(access.get("self-serve", 0) / len(rows), 3) if rows else 0,
        "buildable_share": round(build.get("yes", 0) / len(rows), 3) if rows else 0,
        "oauth_share": round(auth.get("OAuth2", 0) / len(rows), 3) if rows else 0,
    }
    DATA_DIR.mkdir(exist_ok=True)
    INSIGHTS_PATH.write_text(json.dumps(insights, indent=2), encoding="utf-8")

    print(f"Apps analysed: {insights['total']}")
    print(f"Auth: {insights['auth']}")
    print(f"Access: {insights['access']}")
    print(f"Buildability: {insights['buildability']}")
    print(f"Self-serve share: {insights['self_serve_share']} | OAuth share: {insights['oauth_share']}")
    print(f"Easy wins: {len(easy)} | Needs outreach: {len(outreach)} | No public API: {len(no_api)}")
    print(f"Top blockers: {insights['top_blockers']}")
    print(f"-> {INSIGHTS_PATH}")


if __name__ == "__main__":
    main()
