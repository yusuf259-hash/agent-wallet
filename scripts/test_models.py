import os

import requests
from dotenv import load_dotenv

load_dotenv()
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
HEADERS = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

for model in MODELS:
    try:
        r = requests.post(
            URL, headers=HEADERS, json={"model": model, "input": "Say hi"}, timeout=40
        )
        note = r.text[:110].replace("\n", " ")
        print(f"{model:24} {r.status_code}  {note}")
    except Exception as e:
        print(f"{model:24} failed: {type(e).__name__}")