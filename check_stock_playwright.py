#!/usr/bin/env python3
import os
import json
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from messaging_api import push_text
from bs4 import BeautifulSoup

load_dotenv()

COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "5"))
def can_notify(entry):
    last_ts = entry.get("last_notify_ts")
    if not last_ts:
        return True
    return (int(time.time()) - int(last_ts)) >= COOLDOWN_MINUTES * 60


LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TO_USER_ID = os.getenv("LINE_TO_USER_ID")
NOTIFY_PREFIX = os.getenv("NOTIFY_PREFIX", "🔔 再入荷")
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0")
TARGETS_PATH = os.getenv("TARGETS_PATH", "targets.json")
STATE_PATH = os.getenv("STATE_PATH", "state.json")
TIMEOUT = int(os.getenv("TIMEOUT", "30"))

def send_line_notify(message: str):
    # Backward name kept. Uses Messaging API push.
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_TO_USER_ID:
        print('WARN: LINE_CHANNEL_ACCESS_TOKEN or LINE_TO_USER_ID not set; skip notify')
        return
    try:
        status, body = push_text(LINE_TO_USER_ID, message, LINE_CHANNEL_ACCESS_TOKEN)
        print(f'LINE Messaging API push: {status} {body}')
    except Exception as e:
        print(f'LINE push error: {e}')
    return
    import requests
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}
    data = {"message": message}
    try:
        resp = requests.post(url, headers=headers, data=data, timeout=TIMEOUT)
        print(f"LINE Notify status: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"LINE Notify error: {e}")

@dataclass
class Target:
    name: str
    url: str
    in_stock_css: str
    in_stock_text_contains: Optional[List[str]] = None
    out_of_stock_css: Optional[str] = None
    out_of_stock_text_contains: Optional[List[str]] = None

def load_targets(path: str) -> List[Target]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Target(**item) for item in data]

def load_state(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(path: str, state: Dict[str, Any]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def decide_stock(html: str, t: Target) -> Optional[bool]:
    soup = BeautifulSoup(html, "html.parser")
    def text_contains_any(text, needles):
        if not needles: return False
        t = (text or "").strip()
        return any(s for s in needles if s and s in t)
    try:
        if t.in_stock_css:
            for node in soup.select(t.in_stock_css):
                txt = node.get_text(separator=" ", strip=True)
                if (t.in_stock_text_contains and text_contains_any(txt, t.in_stock_text_contains)) or (t.in_stock_text_contains is None):
                    return True
        if t.out_of_stock_css:
            for node in soup.select(t.out_of_stock_css):
                txt = node.get_text(separator=" ", strip=True)
                if (t.out_of_stock_text_contains and text_contains_any(txt, t.out_of_stock_text_contains)) or (t.out_of_stock_text_contains is None):
                    return False
    except Exception as e:
        print(f"parse error: {e}")
    return None

def render_with_playwright(url: str) -> str:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=USER_AGENT, java_script_enabled=True)
        page = ctx.new_page()
        page.set_default_timeout(TIMEOUT * 1000)
        page.goto(url, wait_until="networkidle")
        html = page.content()
        browser.close()
        return html

def main():
    targets = load_targets(TARGETS_PATH)
    state = load_state(STATE_PATH)

    for t in targets:
        try:
            html = render_with_playwright(t.url)
        except Exception as e:
            print(f"Playwright fetch error: {e}")
            continue

        decision = decide_stock(html, t)
        key = t.url
        prev = state.get(key, {}).get("in_stock")
        now = decision
        print(f"[{t.name}] decision={now} prev={prev} url={t.url}")

        if now is True and prev is not True and can_notify(state.get(key, {})):
            msg = f"{NOTIFY_PREFIX}\n{t.name}\n在庫が復活したかもしれません！\n{t.url}"
            send_line_notify(msg)
            state[key] = {**state.get(key, {}), "last_notify_ts": int(time.time())}

        state[key] = {"in_stock": now, "ts": int(time.time())}

    save_state(STATE_PATH, state)

if __name__ == "__main__":
    main()
