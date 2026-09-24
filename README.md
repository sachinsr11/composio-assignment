# 10-App Pilot — Agent Buildability Study

An agent researches **10 of 100 target apps** (one per category: auth, self-serve vs gated, API
surface, MCP), derives a buildability verdict, clusters the patterns observed in the pilot, and
ships one self-explanatory HTML page. The remaining 90 apps are left for scaling after
verification.

Built with the current **Composio v3 session SDK** (`composio` + `composio_gemini`) for tool
discovery/execution and **Gemini** (`google-genai`) for structured extraction.

## How the agent works

Per app:

1. **Discover** the search + scrape tool slugs at runtime via the session meta-tool
   `COMPOSIO_SEARCH_TOOLS` (nothing hardcoded).
2. **Gather** official docs with those Composio tools.
3. **Extract** category, description, auth methods, access (self-serve/gated), API surface and
   MCP status with Gemini (JSON output).
4. **Derive the buildability verdict LAST** — a deterministic rule applied only after the other
   fields are known, so it is never guessed before the evidence.

Then `verify.py` re-fetches fresh evidence and audits every field, and a human checklist scores
the first pass against ground truth to show accuracy movement.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then fill in your keys
```

`.env`:

```
COMPOSIO_API_KEY=...
GOOGLE_API_KEY=...
GEMINI_MODEL=gemini-3.5-flash-lite
```

## Run

```powershell
python src/research_agent.py --pilot   # 10 apps, one per category (do this first)
python src/verify.py                   # agent self-check + human checklist
python src/analyze.py                  # patterns -> data/insights.json
python src/generate_report.py          # -> index.html
# then, for the remaining 90:
python src/research_agent.py --all
python src/analyze.py; python src/generate_report.py
```

Results are incremental and resumable in `data/raw_results.json`. Use `--force` to redo apps.

## Verification

1. `verify.py` writes `data/human_checklist.csv` (one app per category).
2. Fill the `human_value` column from the cited docs, then save as
   `data/human_corrections.json` in the shape `{"<app id>": {"<field>": <correct value>}}`.
3. Re-run `python src/verify.py` to compute first-pass vs after-loop accuracy in
   `data/accuracy.json` (shown on the page).

## Files

| Path | Purpose |
| --- | --- |
| `apps.csv` | The 100-app input. |
| `src/research_agent.py` | Composio gather + Gemini extraction; verdict derived last. |
| `src/verify.py` | Agent self-check + human checklist + accuracy. |
| `src/analyze.py` | Pattern clustering → `data/insights.json`. |
| `src/generate_report.py` | Builds the single-file `index.html`. |
| `index.html` | The deliverable. |

## Deploy

GitHub Pages serves `index.html` from the repository root on `main`. No build step.
