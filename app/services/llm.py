import os
import requests
from app.config import OPENROUTER_API_KEY, OPENROUTER_URL, MODEL_ID

def query_openrouter(messages, model=MODEL_ID, temperature=0.7):
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()