"""Build the single-file deliverable: index.html.

Reads data/raw_results.json + data/insights.json (+ verification if present),
embeds everything as JSON, and renders the case study with vanilla JS.

Usage: python src/generate_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_PATH = DATA_DIR / "raw_results.json"
INSIGHTS_PATH = DATA_DIR / "insights.json"
AGENT_PATH = DATA_DIR / "agent_verification.json"
ACCURACY_PATH = DATA_DIR / "accuracy.json"
OUT_PATH = ROOT / "index.html"

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>10-App Pilot — Agent Buildability Study</title>
<style>
  :root { --bg:#0b0f17; --panel:#131a26; --panel-2:#182235; --line:#2a3951; --txt:#e6edf6; --mut:#9eacc1; --acc:#78b0ff;
          --yes:#1f8a4c; --partial:#a8760a; --no:#b3363f; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--txt); font:15px/1.6 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  a { color:var(--acc); }
  header { padding:56px 24px 30px; border-bottom:1px solid var(--line); background:radial-gradient(circle at 12% 0%,#1b3557 0,#101a2b 38%,#0b0f17 78%); }
  .wrap { max-width:1240px; margin:0 auto; }
  h1 { max-width:850px; margin:0 0 10px; font-size:clamp(30px,5vw,48px); line-height:1.08; letter-spacing:-1.2px; }
  h2 { margin:38px 0 12px; font-size:22px; letter-spacing:-.25px; }
  h3 { margin:0 0 5px; font-size:16px; }
  .sub { max-width:900px; color:var(--mut); margin:0; font-size:16px; }
  section { padding:12px 24px 24px; }
  .eyebrow { margin:0 0 12px; color:var(--acc); font-size:12px; font-weight:700; letter-spacing:1.2px; text-transform:uppercase; }
  .pilot-note { margin:22px 0 4px; padding:12px 15px; background:rgba(120,176,255,.1); border:1px solid rgba(120,176,255,.35); border-radius:10px; color:#d5e5fb; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:18px 0; }
  .card { background:linear-gradient(145deg,var(--panel-2),var(--panel)); border:1px solid var(--line); border-radius:12px; padding:16px; }
  .card .n { font-size:30px; line-height:1.1; font-weight:750; }
  .card .l { color:var(--mut); font-size:12px; text-transform:uppercase; letter-spacing:.5px; }
  .cols { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
  @media (max-width:820px){ .cols{ grid-template-columns:1fr; } }
  ul { margin:6px 0 0; padding-left:18px; }
  li { margin:4px 0; }
  .controls { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0; align-items:center; }
  input, select, button { background:var(--panel); color:var(--txt); border:1px solid var(--line); border-radius:8px; padding:8px 10px; font-size:14px; }
  button { cursor:pointer; }
  button.active { border-color:var(--acc); color:var(--acc); }
  .table-wrap { overflow-x:auto; border:1px solid var(--line); border-radius:10px; }
  table { width:100%; min-width:980px; border-collapse:collapse; font-size:13.5px; }
  th, td { text-align:left; padding:11px 12px; border-bottom:1px solid var(--line); vertical-align:top; }
  th { position:sticky; top:0; background:#0f1622; cursor:pointer; z-index:1; white-space:nowrap; }
  tr:hover td { background:#101826; }
  .badge { display:inline-block; padding:2px 8px; border-radius:20px; font-size:11.5px; font-weight:600; white-space:nowrap; }
  .b-yes{ background:rgba(31,138,76,.18); color:#57d18c; }
  .b-partial{ background:rgba(168,118,10,.18); color:#e5b24a; }
  .b-no{ background:rgba(179,54,63,.18); color:#ff8a92; }
  .chip{ display:inline-block; padding:1px 7px; margin:1px 3px 1px 0; border:1px solid var(--line); border-radius:6px; color:var(--mut); font-size:11.5px; }
  .muted{ color:var(--mut); }
  code { background:#0a0f18; border:1px solid var(--line); border-radius:6px; padding:1px 6px; font-size:12.5px; }
  pre { background:#0a0f18; border:1px solid var(--line); border-radius:10px; padding:14px; overflow:auto; font-size:12.5px; }
  .note { background:#101826; border-left:3px solid var(--acc); padding:12px 15px; border-radius:0 8px 8px 0; color:#c9d6ea; }
  footer { padding:24px; color:var(--mut); border-top:1px solid var(--line); margin-top:30px; }
  .pill{ font-size:12px; color:var(--mut); }
</style>
</head>
<body>
<header>
  <div class="wrap">
    <p class="eyebrow">Research case study · pilot stage</p>
    <h1>10-App Pilot → Agent Toolkits: What's Buildable Today</h1>
    <p class="sub">An agent researched auth, access gates and API surface for <b>10 of 100 target apps</b> (one per category). Patterns below are drawn from this pilot only and are not presented as representative of the full 100. <span id="stamp" class="pill"></span></p>
    <p class="pilot-note"><b>Read this as a pilot, not a final market estimate.</b> The next step is human verification, prompt tuning, and then research on the remaining 90 apps.</p>
  </div>
</header>

<section class="wrap">
  <div class="cards" id="cards"></div>
  <div class="cols">
    <div>
      <h2>Headline patterns</h2>
      <ul id="patterns"></ul>
    </div>
    <div>
      <h2>Where the friction is</h2>
      <ul id="friction"></ul>
    </div>
  </div>
</section>

<section class="wrap">
  <h2>Pilot results — 10 of 100 target apps</h2>
  <div class="controls">
    <input id="q" placeholder="Search app, category, auth…" style="min-width:260px" />
    <button data-f="all" class="active">All</button>
    <button data-f="yes">Buildable now</button>
    <button data-f="partial">Partial</button>
    <button data-f="no">Gated / blocked</button>
    <span class="muted" id="count"></span>
  </div>
  <div class="table-wrap">
  <table>
    <thead><tr>
      <th data-k="app">App</th><th data-k="category">Category</th><th data-k="auth">Auth</th>
      <th data-k="access">Access</th><th data-k="api">API</th><th data-k="mcp">MCP</th>
      <th data-k="buildability">Buildability</th><th data-k="main_blocker">Main blocker</th><th>Evidence</th>
    </tr></thead>
    <tbody id="rows"></tbody>
  </table>
  </div>
</section>

<section class="wrap cols">
  <div>
    <h2>The agent</h2>
    <div id="agent"></div>
  </div>
  <div>
    <h2>Verification</h2>
    <div id="verify"></div>
  </div>
</section>

<footer class="wrap">
  <div id="foot"></div>
</footer>

<script>
const DATA = /*__DATA__*/;
const { apps, insights, verification, accuracy } = DATA;
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pct = n => Math.round(n*100) + "%";

document.getElementById("stamp").textContent = "Generated " + DATA.generated;

const cards = [
  [apps.length, "Apps researched"],
  [pct(insights.oauth_share), "Use OAuth2"],
  [pct(insights.self_serve_share), "Self-serve access"],
  [insights.buildability.yes || 0, "Buildable now"],
  [(insights.needs_outreach||[]).length, "Need outreach"],
  [(insights.no_public_api||[]).length, "No public API"],
];
document.getElementById("cards").innerHTML = cards.map(([n,l]) =>
  `<div class="card"><div class="n">${esc(n)}</div><div class="l">${esc(l)}</div></div>`).join("");

const topAuth = Object.entries(insights.auth).slice(0,4).map(([k,v])=>`${k} (${v})`).join(", ");
const topAccess = Object.entries(insights.access).slice(0,4).map(([k,v])=>`${k} (${v})`).join(", ");
const patterns = [
  `<b>Pilot:</b> <b>${pct(insights.oauth_share)}</b> of the 10 apps use <b>OAuth2</b> — the dominant auth pattern so far. Auth mix: ${esc(topAuth)}.`,
  `<b>Pilot:</b> <b>${pct(insights.self_serve_share)}</b> offer self-serve credentials. Access mix: ${esc(topAccess)}.`,
  `<b>Pilot:</b> <b>${insights.buildability.yes||0}</b> are buildable today, <b>${insights.buildability.partial||0}</b> partial, <b>${insights.buildability.no||0}</b> blocked.`,
  `<b>Pilot MCP landscape:</b> ${esc(Object.entries(insights.mcp).map(([k,v])=>`${k} (${v})`).join(", "))}.`,
];
document.getElementById("patterns").innerHTML = patterns.map(p=>`<li>${p}</li>`).join("");

const blockers = Object.entries(insights.top_blockers).slice(0,6);
document.getElementById("friction").innerHTML =
  `<li><b>Pilot:</b> Most common blocker: <b>${esc(blockers[0]?.[0] || "n/a")}</b>${blockers[0]?` (${blockers[0][1]} of 10)`:""}.</li>` +
  blockers.slice(1).map(([k,v])=>`<li><b>Pilot:</b> ${esc(k)} — ${v} of 10</li>`).join("") +
  `<li><b>Pilot easy wins</b> (self-serve + public API): <b>${(insights.easy_wins||[]).length}</b> of 10 apps.</li>`;

const accessColor = a => ({"self-serve":"b-yes","free-trial":"b-partial","paid-plan":"b-partial","admin-approval":"b-no","partnership":"b-no","contact-sales":"b-no"}[a] || "");
let filter = "all", sortKey = "app", asc = true;

function render(){
  const q = document.getElementById("q").value.toLowerCase();
  let rows = apps.filter(r => filter==="all" || r.buildability===filter);
  if (q) rows = rows.filter(r => JSON.stringify(r).toLowerCase().includes(q));
  rows.sort((a,b)=>{
    const va = (sortKey==="auth"? (a.auth_methods||[]).join(",") : a[sortKey]) ?? "";
    const vb = (sortKey==="auth"? (b.auth_methods||[]).join(",") : b[sortKey]) ?? "";
    return (String(va).localeCompare(String(vb)))*(asc?1:-1);
  });
  document.getElementById("count").textContent = rows.length + " shown";
  document.getElementById("rows").innerHTML = rows.map(r=>{
    const auth = (r.auth_methods||[]).map(m=>`<span class="chip">${esc(m)}</span>`).join("");
    const api = (r.api_types||[]).map(t=>`<span class="chip">${esc(t)}</span>`).join("") + `<div class="muted">${esc(r.api_breadth)}</div>`;
    const ev = (r.evidence_urls||[]).slice(0,1).map(u=>`<a href="${esc(u)}" target="_blank" rel="noopener">docs</a>`).join("") || `<span class="muted">—</span>`;
    return `<tr>
      <td><b>${esc(r.app)}</b></td>
      <td class="muted">${esc(r.category)}</td>
      <td>${auth||'<span class="muted">unknown</span>'}</td>
      <td><span class="badge ${accessColor(r.access)}">${esc(r.access)}</span></td>
      <td>${api}</td>
      <td>${esc(r.mcp)}</td>
      <td><span class="badge b-${esc(r.buildability)}">${esc(r.buildability)}</span></td>
      <td class="muted">${esc(r.main_blocker||"—")}</td>
      <td>${ev}</td>
    </tr>`;
  }).join("");
}
document.querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{
  const k = th.dataset.k; asc = sortKey===k ? !asc : true; sortKey = k; render();
});
document.querySelectorAll("button[data-f]").forEach(b=>b.onclick=()=>{
  document.querySelectorAll("button[data-f]").forEach(x=>x.classList.remove("active"));
  b.classList.add("active"); filter = b.dataset.f; render();
});
document.getElementById("q").oninput = render;

document.getElementById("agent").innerHTML = `
  <p>One agent per app, built on <b>Composio v3 sessions</b> + <b>Gemini</b>:</p>
  <ol>
    <li><b>Discover</b> search/scrape tool slugs at runtime with <code>COMPOSIO_SEARCH_TOOLS</code> (nothing hardcoded).</li>
    <li><b>Gather</b> official docs via those Composio tools.</li>
    <li><b>Extract</b> category, auth, access and API surface with Gemini (JSON output).</li>
    <li><b>Derive the buildability verdict last</b>, from the facts above — never guessed upfront.</li>
  </ol>
  <p class="note"><b>Where a human is needed:</b> review ambiguous access classifications and validate cited evidence before scaling to the remaining 90 apps.</p>`;

const v = verification?.summary;
let vhtml = `<p>Verification is the next step in the pipeline. The repository contains the verification workflow and checklist (<code>src/verify.py</code>, <code>data/human_checklist.csv</code>) for reproducibility.</p>`;
if (v) {
  vhtml += `<p>The agent re-fetched fresh evidence and audited each field against it (skeptical re-prompt).</p>`;
  vhtml += `<p><b>Agent self-check:</b> ${pct(v.accuracy)} of fields supported (${v.correct}/${v.fields}) across ${v.apps} apps.</p>`;
}
if (accuracy) {
  vhtml += `<p><b>Human ground truth</b> on ${accuracy.human_checked_apps} apps:
    first pass <b>${pct(accuracy.first_pass.accuracy)}</b> → after verification loop <b>${pct(accuracy.after_agent_loop.accuracy)}</b>.</p>`;
  vhtml += `<table><thead><tr><th>Field</th><th>1st pass</th><th>After loop</th></tr></thead><tbody>` +
    Object.entries(accuracy.per_field).map(([f,d])=>`<tr><td>${esc(f)}</td><td>${pct(d.first_accuracy)}</td><td>${pct(d.fixed_accuracy)}</td></tr>`).join("") +
    `</tbody></table>`;
} else {
  vhtml += `<p class="muted"><b>Agent self-check and human verification are pending.</b> Run <code>python src/verify.py</code> to produce the agent audit and human checklist, then fill <code>data/human_corrections.json</code> and re-run.</p>`;
}
if (verification?.apps) {
  const misses = verification.apps.filter(a=>a.correct < a.total).slice(0,6);
  if (misses.length) vhtml += `<p><b>Honest misses:</b></p><ul>` + misses.map(a=>`<li>${esc(a.app)} — ${a.correct}/${a.total} fields supported</li>`).join("") + `</ul>`;
}
document.getElementById("verify").innerHTML = vhtml;

document.getElementById("foot").innerHTML =
  `<p>Source: <a href="https://github.com/" id="repo">repository</a> · <a href="data/raw_results.json">raw results JSON</a> · <a href="data/insights.json">insights JSON</a></p>
   <p class="muted">Method: 10-app pilot using Composio session tools for gathering, Gemini for extraction, and a deterministic rule for the buildability verdict. Gated is a finding, not a failure.</p>`;

render();
</script>
</body>
</html>
"""


def main() -> None:
    rows = json.loads(RAW_PATH.read_text(encoding="utf-8-sig"))
    apps = [r for r in rows.values() if "error" not in r]
    apps.sort(key=lambda r: r.get("id", 0))
    insights = json.loads(INSIGHTS_PATH.read_text(encoding="utf-8-sig")) if INSIGHTS_PATH.exists() else {}
    verification = json.loads(AGENT_PATH.read_text(encoding="utf-8-sig")) if AGENT_PATH.exists() else None
    accuracy = json.loads(ACCURACY_PATH.read_text(encoding="utf-8-sig")) if ACCURACY_PATH.exists() else None

    payload = {
        "apps": apps,
        "insights": insights,
        "verification": verification,
        "accuracy": accuracy,
        "generated": __import__("time").strftime("%Y-%m-%d %H:%M"),
    }
    data_js = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    OUT_PATH.write_text(TEMPLATE.replace("/*__DATA__*/", data_js), encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(apps)} apps)")


if __name__ == "__main__":
    main()
