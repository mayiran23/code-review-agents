import db
import requests

WEBHOOK = "https://hooks.example.com/abc123"


def sync_user(user):
    db.insert("users", user)
    requests.post(WEBHOOK, json=user)
