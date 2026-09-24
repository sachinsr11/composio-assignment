import os
from dotenv import load_dotenv
load_dotenv()
from google import genai

client = genai.Client()
print("Listing models that support generateContent:\n")
for m in client.models.list():
    actions = getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or []
    if not actions or "generateContent" in actions:
        print(f"  {m.name:55s} {actions}")
