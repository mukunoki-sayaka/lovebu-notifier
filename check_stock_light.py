#!/usr/bin/env python3
import os, json, time, hashlib, random
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

HEADERS_PATH = os.getenv("HEADERS_PATH", "headers_cache.json")
STATE_PATH = os.getenv("STATE_PATH", "state.json")
TARGETS_PATH = os.getenv("TARGETS_PATH", "targets.json")
TIMEOUT = int(os.getenv("TIMEOUT", "20"))
TRIGGER_PATH = os.getenv("TRIGGER_PATH", "needs_confirm.json")
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (compatible)")

BASE_HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}

@dataclass
class Target:
    name: str
    url: str
    in_stock_css: str
    in_stock_text_contains: Optional[List[str]] = None
    out_of_stock_css: Optional[str] = None
    out_of_stock_text_contains: Optional[List[str]] = None

def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_targets() -> List[Target]:
    data = load_json(TARGETS_PATH, [])
    return [Target(**x) for x in data]

def decide_stock_html(html: str, t: Target) -> Optional[bool]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    def contains_any(text, needles: Optional[List[str]]):
        if not needles: return False
        tx = (text or "").strip()
        return any((s in tx) for s in needles if s)

    # Try in-stock selectors first
    if t.in_stock_css:
        for node in soup.select(t.in_stock_css):
            txt = node.get_text(separator=" ", strip=True)
            if t.in_stock_text_contains is None or contains_any(txt, t.in_stock_text_contains):
                return True

    if t.out_of_stock_css:
        for node in soup.select(t.out_of_stock_css):
            txt = node.get_text(separator=" ", strip=True)
            if t.out_of_stock_text_contains is None or contains_any(txt, t.out_of_stock_text_contains):
                return False

    return None

def conditional_get(url: str, headers_cache: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    h = dict(BASE_HEADERS)
    meta = headers_cache.get(url, {})
    if "etag" in meta:
        h["If-None-Match"] = meta["etag"]
    if "last_modified" in meta:
        h["If-Modified-Since"] = meta["last_modified"]
    try:
        resp = requests.get(url, headers=h, timeout=TIMEOUT)
        if resp.status_code == 304:
            return {"status": 304, "html": None, "etag": meta.get("etag"), "last_modified": meta.get("last_modified")}
        etag = resp.headers.get("ETag")
        last_modified = resp.headers.get("Last-Modified")
        return {"status": resp.status_code, "html": resp.text if resp.status_code == 200 else None, "etag": etag, "last_modified": last_modified}
    except Exception as e:
        print(f"ERROR GET {url}: {e}")
        return {"status": 0, "html": None, "etag": meta.get("etag"), "last_modified": meta.get("last_modified")}

def main():
    # Light jitter to avoid synchronized hits
    time.sleep(random.randint(0, 20))

    targets = load_targets()
    state = load_json(STATE_PATH, {})
    headers_cache = load_json(HEADERS_PATH, {})
    needs_confirm = []

    for t in targets:
        res = conditional_get(t.url, headers_cache)
        print(f"GET {t.url} -> {res['status']}")
        if res["status"] == 304:
            # No content change; keep previous decision
            decision = state.get(t.url, {}).get("in_stock")
        elif res["status"] == 200 and res["html"]:
            decision = decide_stock_html(res["html"], t)
            # Update header cache
            headers_cache[t.url] = {
                "etag": res.get("etag"),
                "last_modified": res.get("last_modified")
            }
        else:
            decision = state.get(t.url, {}).get("in_stock")

        prev = state.get(t.url, {}).get("in_stock")
        print(f"[light] {t.name}: prev={prev} now={decision}")

        # If potential in-stock (True) and previously not True -> trigger heavy confirm
        if decision is True and prev is not True:
            needs_confirm.append({"name": t.name, "url": t.url})

        state[t.url] = {
            "in_stock": decision,
            "ts": int(time.time()),
            # keep last_notify_ts if exists (playwright will maintain it)
            **({"last_notify_ts": state[t.url]["last_notify_ts"]} if t.url in state and "last_notify_ts" in state[t.url] else {})
        }

    if needs_confirm:
        with open(TRIGGER_PATH, "w", encoding="utf-8") as f:
            json.dump(needs_confirm, f, ensure_ascii=False, indent=2)

    save_json(STATE_PATH, state)
    save_json(HEADERS_PATH, headers_cache)

if __name__ == "__main__":
    main()
