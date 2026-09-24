"""Verification loop for the research results.

Two loops:
  1. Agent self-check: re-gather fresh evidence for a sample and ask Gemini to
     audit every extracted field, returning a corrected value when wrong.
  2. Human check: emit a checklist (one app per category by default) and, once
     `data/human_corrections.json` exists, score the first pass and the
     agent-corrected pass against it.

Usage:
  python src/verify.py                  # self-check 10 apps (one per category) + emit checklist
  python src/verify.py --all            # audit every app in raw_results.json
  python src/verify.py --all --force    # re-audit apps already in the report
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from dotenv import load_dotenv

from research_agent import Researcher, load_raw, parse_json

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_PATH = DATA_DIR / "raw_results.json"
AGENT_PATH = DATA_DIR / "agent_verification.json"
HUMAN_PATH = DATA_DIR / "human_corrections.json"
CHECKLIST_PATH = DATA_DIR / "human_checklist.csv"
ACCURACY_PATH = DATA_DIR / "accuracy.json"

CHECK_FIELDS = [
    "category",
    "auth_methods",
    "access",
    "api_types",
    "api_breadth",
    "mcp",
    "main_blocker",
]

AUDIT_PROMPT = """You are auditing a research extraction against fresh web evidence. Be skeptical and precise.

APP: {app}
FRESH EVIDENCE:
{evidence}

EXTRACTED FACTS:
{facts}

For EVERY field below, decide if the extracted value is supported by the evidence.
Return ONLY JSON:
{{
  "category": {{"correct": true/false, "corrected": <value>, "note": "why"}},
  "auth_methods": {{"correct": true/false, "corrected": [..], "note": "why"}},
  "access": {{"correct": true/false, "corrected": <value>, "note": "why"}},
  "api_types": {{"correct": true/false, "corrected": [..], "note": "why"}},
  "api_breadth": {{"correct": true/false, "corrected": <value>, "note": "why"}},
  "mcp": {{"correct": true/false, "corrected": <value>, "note": "why"}},
  "main_blocker": {{"correct": true/false, "corrected": <value>, "note": "why"}}
}}
Every field must be present. Use the extracted value as "corrected" when it is right.
"""


def norm(value) -> str:
    if isinstance(value, list):
        return "|".join(sorted(v.strip().lower() for v in value if str(v).strip()))
    return str(value or "").strip().lower()


def fields_match(a, b) -> bool:
    na, nb = norm(a), norm(b)
    if not na and not nb:
        return True
    return na == nb


def sample(raw: dict, n: int | None) -> list[dict]:
    rows = [raw[k] for k in sorted(raw, key=lambda x: int(x))]
    if n is None:
        return rows
    picked: list[dict] = []
    seen: set[str] = set()
    # First pass: one app per category (spread across the dataset).
    for row in rows:
        cat = row.get("category_graph", row.get("category", ""))
        if cat not in seen:
            seen.add(cat)
            picked.append(row)
        if len(picked) >= n:
            return picked
    # Second pass: fill up to n with the remaining apps.
    for row in rows:
        if row in picked:
            continue
        picked.append(row)
        if len(picked) >= n:
            break
    return picked


def audit(researcher: Researcher, row: dict) -> dict:
    from google.genai import types

    evidence, _ = researcher.gather(row["app"], row.get("hint", ""))
    facts = {f: row.get(f) for f in CHECK_FIELDS}
    prompt = AUDIT_PROMPT.format(app=row["app"], evidence=evidence, facts=json.dumps(facts, indent=2))
    last = None
    for model in researcher.model_chain():
        for attempt in range(3):
            try:
                resp = researcher.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json",
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    ),
                )
                return parse_json(resp.text)
            except Exception as exc:  # noqa: BLE001
                time.sleep(3 * (attempt + 1))
                last = exc
    return {"error": str(last)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-audit apps already in the report")
    args = ap.parse_args()

    if not RAW_PATH.exists():
        raise SystemExit("Run research_agent.py first.")
    raw = load_raw()
    rows = sample(raw, None if args.all else args.n)

    researcher = Researcher()
    researcher.discover()

    report: dict = {"apps": [], "summary": {}}
    done: dict[str, dict] = {}
    if AGENT_PATH.exists() and not args.force:
        try:
            prev = json.loads(AGENT_PATH.read_text(encoding="utf-8-sig"))
            done = {str(a["id"]): a for a in prev.get("apps", [])}
        except Exception:  # noqa: BLE001
            done = {}

    def write_report() -> None:
        correct = sum(a["correct"] for a in report["apps"])
        total = sum(a["total"] for a in report["apps"])
        report["summary"] = {
            "apps": len(report["apps"]),
            "fields": total,
            "correct": correct,
            "accuracy": round(correct / total, 3) if total else 0,
        }
        DATA_DIR.mkdir(exist_ok=True)
        AGENT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    for i, row in enumerate(rows, 1):
        key = str(row["id"])
        if key in done:
            report["apps"].append(done[key])
            print(f"[{i}/{len(rows)}] skip {row['app']} (cached audit)")
            continue
        print(f"[{i}/{len(rows)}] audit {row['app']}")
        result = audit(researcher, row)
        entry = {"id": row["id"], "app": row["app"], "fields": {}, "correct": 0, "total": 0}
        for field in CHECK_FIELDS:
            verdict = result.get(field) if isinstance(result, dict) else None
            if not isinstance(verdict, dict):
                continue
            ok = bool(verdict.get("correct"))
            entry["fields"][field] = {
                "agent": row.get(field),
                "correct": ok,
                "corrected": verdict.get("corrected"),
                "note": verdict.get("note", ""),
            }
            entry["total"] += 1
            entry["correct"] += int(ok)
        entry["accuracy"] = round(entry["correct"] / entry["total"], 3) if entry["total"] else 0
        report["apps"].append(entry)
        write_report()
        print(f"  {entry['correct']}/{entry['total']} fields supported")

    write_report()
    correct = report["summary"]["correct"]
    total = report["summary"]["fields"]

    with CHECKLIST_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "app", "field", "agent_value", "evidence_url", "human_value"])
        for row in rows:
            evidence = (row.get("evidence_urls") or [""])[0]
            for field in CHECK_FIELDS:
                writer.writerow([row["id"], row["app"], field, json.dumps(row.get(field)), evidence, ""])

    print(f"\nAgent self-check accuracy: {report['summary']['accuracy']} ({correct}/{total})")
    print(f"Checklist -> {CHECKLIST_PATH}")
    print(f"Report    -> {AGENT_PATH}")

    if HUMAN_PATH.exists():
        score_human(raw)


def score_human(raw: dict) -> None:
    corrections = json.loads(HUMAN_PATH.read_text(encoding="utf-8-sig"))
    agent = json.loads(AGENT_PATH.read_text(encoding="utf-8-sig"))
    agent_by_id = {str(a["id"]): a for a in agent.get("apps", [])}

    first_correct = first_total = fixed_correct = fixed_total = 0
    per_field: dict[str, dict] = {}
    for app_id, truth in corrections.items():
        row = raw.get(app_id)
        if not row:
            continue
        audited = agent_by_id.get(app_id, {}).get("fields", {})
        for field, expected in truth.items():
            if field not in CHECK_FIELDS:
                continue
            first_total += 1
            first_ok = fields_match(row.get(field), expected)
            first_correct += int(first_ok)

            corrected = audited.get(field, {}).get("corrected", row.get(field))
            if audited.get(field, {}).get("correct"):
                corrected = row.get(field)
            fixed_total += 1
            fixed_ok = fields_match(corrected, expected)
            fixed_correct += int(fixed_ok)

            bucket = per_field.setdefault(field, {"checked": 0, "first": 0, "fixed": 0})
            bucket["checked"] += 1
            bucket["first"] += int(first_ok)
            bucket["fixed"] += int(fixed_ok)

    result = {
        "human_checked_apps": len(corrections),
        "first_pass": {
            "correct": first_correct,
            "total": first_total,
            "accuracy": round(first_correct / first_total, 3) if first_total else 0,
        },
        "after_agent_loop": {
            "correct": fixed_correct,
            "total": fixed_total,
            "accuracy": round(fixed_correct / fixed_total, 3) if fixed_total else 0,
        },
        "per_field": {
            f: {
                "checked": v["checked"],
                "first_accuracy": round(v["first"] / v["checked"], 3),
                "fixed_accuracy": round(v["fixed"] / v["checked"], 3),
            }
            for f, v in per_field.items()
        },
    }
    ACCURACY_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nHuman-checked apps: {len(corrections)}")
    print(f"First pass:      {result['first_pass']['accuracy']}")
    print(f"After agent loop:{result['after_agent_loop']['accuracy']}")
    print(f"Accuracy -> {ACCURACY_PATH}")


if __name__ == "__main__":
    main()
