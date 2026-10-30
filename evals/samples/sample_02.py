import requests

API_KEY = "sk-9f3a8b2c7d1e4f5a6b8c9d0e1f2a3b4c"


def call_llm(prompt):
    return requests.post(
        "https://api.example.com/v1/chat",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"prompt": prompt},
    )
