#!/usr/bin/env python3
import os, json
import requests

LINE_MESSAGING_PUSH_URL = "https://api.line.me/v2/bot/message/push"

def push_text(to_user_id: str, text: str, channel_access_token: str):
    headers = {
        "Authorization": f"Bearer {channel_access_token}",
        "Content-Type": "application/json"
    }
    body = {
        "to": to_user_id,
        "messages": [ { "type": "text", "text": text } ]
    }
    resp = requests.post(LINE_MESSAGING_PUSH_URL, headers=headers, data=json.dumps(body), timeout=20)
    return resp.status_code, resp.text[:500]
