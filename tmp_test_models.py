import os, time, json
from dotenv import load_dotenv
load_dotenv()
from google import genai
from google.genai import types

client = genai.Client()
models = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]
prompt = 'Return ONLY JSON: {"auth":["OAuth2"],"access":"self-serve","api":"REST","confidence":0.9}'
for m in models:
    for attempt in (1, 2):
        t0 = time.time()
        try:
            cfg = types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            )
            try:
                cfg.thinking_config = types.ThinkingConfig(thinking_budget=0)
            except Exception:
                pass
            resp = client.models.generate_content(model=m, contents=prompt, config=cfg)
            txt = (resp.text or "").strip()
            ok = txt.startswith("{")
            print(f"{'OK ' if ok else 'BAD'} {m:26s} try{attempt} {(time.time()-t0):5.1f}s -> {txt[:60]!r}")
            break
        except Exception as exc:
            print(f"FAIL {m:26s} try{attempt} {(time.time()-t0):5.1f}s -> {str(exc)[:80]}")
            time.sleep(2)
