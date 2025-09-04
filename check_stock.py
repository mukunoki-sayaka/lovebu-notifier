#!/usr/bin/env python3
import os
import json
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from messaging_api import push_text

load_dotenv()

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_TO_USER_ID = os.getenv("LINE_TO_USER_ID")
NOTIFY_PREFIX = os.getenv("NOTIFY_PREFIX", "🔔 再入荷")
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0")

TARGETS_PATH = os.getenv("TARGETS_PATH", "targets.json")
STATE_PATH = os.getenv("STATE_PATH", "state.json")
TIMEOUT = int(os.getenv("TIMEOUT", "20"))

HEADERS = {
    "User-Agent": USER_AGENT
}

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
    if not LINE_NOTIFY_TOKEN:
        print("WARN: LINE_NOTIFY_TOKEN not set; skip notify")
        return
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {LINE_NOTIFY_TOKEN}"}
    data = {"message": message}
    try:
        resp = requests.post(url, headers=headers, data=data, timeout=TIMEOUT)
        print(f"LINE Notify status: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"LINE Notify error: {e}")

def text_contains_any(text: str, needles: Optional[List[str]]) -> bool:
    if not needles:
        return False
    t = (text or "").strip()
    for s in needles:
        if s and s in t:
            return True
    return False

def fetch_html(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            return resp.text
        print(f"GET {url} -> {resp.status_code}")
    except Exception as e:
        print(f"Fetch error: {e}")
    return None

def decide_stock(soup: BeautifulSoup, t: Target) -> Optional[bool]:
    # True: in stock, False: out of stock, None: unknown
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

def main():
    targets = load_targets(TARGETS_PATH)
    state = load_state(STATE_PATH)

    for t in targets:
        html = fetch_html(t.url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        decision = decide_stock(soup, t)

        key = t.url
        prev = state.get(key, {}).get("in_stock")
        now = decision

        print(f"[{t.name}] decision={now} prev={prev} url={t.url}")

        # 通知条件： 売り切れ→在庫あり、未知→在庫あり
        if now is True and prev is not True:
            msg = f"{NOTIFY_PREFIX}\n{t.name}\n在庫が復活したかもしれません！\n{t.url}"
            send_line_notify(msg)

        # 状態保存
        state[key] = {"in_stock": now, "ts": int(time.time())}

    save_state(STATE_PATH, state)

if __name__ == "__main__":
    main()
