# 100 Apps → Agent Buildability Study

An agent researches 100 apps (auth, self-serve vs gated, API surface, MCP), derives a
buildability verdict, clusters the patterns, runs an agent self-check on a sample, and ships one
self-explanatory HTML page.

- **Live page:** https://sachinsr11.github.io/composio-assignment/
- **Source:** https://github.com/sachinsr11/composio-assignment

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

Then `verify.py` re-fetches fresh evidence and audits every extracted field with a skeptical
re-prompt (agent self-check). Human accuracy (first pass vs after loop) is scored only when a
human fills `data/human_corrections.json`.

## What is and is not assessed

- **MCP:** the gather step did not target MCP, so it is reported as `not assessed` (91 apps) or
  `official` (9 apps). It is never asserted as `none`.
- **Evidence links** are filtered to documentation pages; favicons, images, and template URLs are
  removed by `clean_urls()`.

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
python src/research_agent.py --all     # all 100 apps (resumable; --force to redo)
python src/verify.py --n 30            # agent self-check on a 30-app sample (resumable)
python src/analyze.py                  # patterns -> data/insights.json
python src/generate_report.py          # -> index.html
```

Results are incremental and resumable in `data/raw_results.json`. `verify.py` is also resumable;
re-run it to continue an interrupted self-check.

## Verification

1. `verify.py` writes `data/agent_verification.json` (agent self-check on the sample) and
   `data/human_checklist.csv`.
2. Fill the `human_value` column from the cited docs, then save as
   `data/human_corrections.json` in the shape `{"<app id>": {"<field>": <correct value>}}`.
3. Re-run `python src/verify.py` to compute first-pass vs after-loop human accuracy in
   `data/accuracy.json` (rendered on the page).

## Files

| Path | Purpose |
| --- | --- |
| `apps.csv` | The 100-app input. |
| `src/research_agent.py` | Composio gather + Gemini extraction; verdict derived last; URL cleaning. |
| `src/verify.py` | Resumable agent self-check + human checklist + accuracy. |
| `src/analyze.py` | Pattern clustering (auth, access-by-category, blocker buckets, MCP) → `data/insights.json`. |
| `src/generate_report.py` | Builds the single-file `index.html`. |
| `index.html` | The deliverable. |

## Deploy

GitHub Pages serves `index.html` from the repository root on `main`. No build step.
