# AGENTS.md

Take-home: research 100 apps (auth, self-serve vs gated, API surface, MCP), cluster patterns, verify, and ship one self-explanatory `index.html` + source repo.

## SDK rules (do not regress)
- Python 3.10. Use `composio` (v3, session-based). Never `composio-core` (legacy v1) or `ComposioToolSet`.
- LLM: `composio_gemini` provider + `google-genai` (`from google import genai`). Never the deprecated `google-generativeai`.
- Init: `composio = Composio(provider=GeminiProvider())` → `session = composio.create(user_id="research_agent")`.
- Execute tools only via `session.execute(tool_slug, arguments=...)`. Session meta-tools (`COMPOSIO_SEARCH_TOOLS`, `COMPOSIO_MANAGE_CONNECTIONS`) fail on the direct/user-id path.
- Discover search + scrape slugs at runtime with `COMPOSIO_SEARCH_TOOLS`. Do not hardcode slugs; optional overrides: `COMPOSIO_SEARCH_SLUG`, `COMPOSIO_SCRAPE_SLUG`.
- v3 terminology: `user_id`, tools, toolkits, auth configs, connected accounts. REST is v3.1 (v3.0 is legacy).

## Constraints
- **Composio-only engine.** No DuckDuckGo / `requests` fallback. If a Composio tool breaks, report it on the page; do not silently substitute another engine.
- Model: `GEMINI_MODEL=gemini-3.5-flash-lite` (15 RPM / 250K TPM / 500 RPD).
- Free-tier capacity is flaky: `gemini-3.5-flash-lite` intermittently 503s. On 503/404, `extract()` walks `GEMINI_FALLBACK_MODELS` (default `gemini-3.5-flash,gemini-3.6-flash,gemini-3.1-flash-lite`). This is model availability, not an engine fallback.
- Verified working model IDs on this key: `gemini-3.5-flash-lite`, `gemini-3.5-flash`, `gemini-3.6-flash`. `gemini-2.5-*` 404s; `gemini-3.1-flash-lite` currently 503s.
- **MCP is NOT assessed** by the current gather step. Never assert `none`; record/report `not assessed` (`analyze.py` maps `none`/`unclear` → `not assessed`).
- Evidence links go through `clean_urls()` (drops favicons/images/template URLs). Keep it.
- Env: `COMPOSIO_API_KEY`, `GOOGLE_API_KEY` (Gemini key). Never commit `.env`.

## Research rule: facts first, verdict last
- Extract category, description, auth methods, access, API surface and MCP status from evidence **first**.
- Only then call `derive_buildability()` to produce `buildability_verdict`. Never infer it before the facts.
- State the main blocker for every gated app with its docs URL as evidence; "gated" is a valid finding, not a failure.

## Analysis rule: only strongly supported patterns
Focus on: dominant auth method (**count apps per method; Bearer token > OAuth2** on this set); self-serve vs gated **by category**; most common blocker categories via `blocker_bucket()`; easy wins (self-serve + public API) vs apps needing outreach (partner / contact-sales / admin-approval). Report MCP as `not assessed`. Add other patterns only if strongly supported.

## Workflow
Do **not** rely on the 10-app `--pilot` for the deliverable; it is a smoke test only. The result is the full 100.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then fill in keys

python src/research_agent.py --all     # all 100 (resumable; --force to redo)
python src/verify.py --n 30            # agent self-check sample (resumable; --all for every app)
python src/analyze.py
python src/generate_report.py
```

`verify.py` saves after every app, so an interrupted run resumes on the next invocation. Human
accuracy (first pass vs after loop) only appears once `data/human_corrections.json` exists — never
claim it otherwise.

## Layout
- `apps.csv` — the 100-app input.
- `src/research_agent.py` — Composio gather + Gemini structured extraction; verdict derived last; URL cleanup; incremental/resumable → `data/raw_results.json`.
- `src/verify.py` — resumable agent self-check vs fresh evidence + human checklist → `data/agent_verification.json`, `data/human_checklist.csv`; `data/accuracy.json` when corrections exist.
- `src/analyze.py` — auth/access/buildability/blocker/MCP clusters → `data/insights.json`.
- `src/generate_report.py` — builds root `index.html` (single file, vanilla JS table; guards against missing insights).
- Deploy: GitHub Pages from `main` root (no build step).
