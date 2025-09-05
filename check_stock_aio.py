# check_stock_aio.py
import asyncio, aiohttp, json, os, hashlib, random, time
from pathlib import Path

DEFAULT_IN_WORDS = ["カートに追加する", "今すぐ購入", "Add to cart", "Buy now"]
DEFAULT_OUT_WORDS = ["在庫切れ", "売り切れ", "SOLD OUT", "在庫なし", "再入荷を通知"]

ROOT = Path(__file__).resolve().parent
F_STATE = ROOT / "state.json"
F_HDRS  = ROOT / "headers_cache.json"
F_NEED  = ROOT / "needs_confirm.json"
F_TARGETS = ROOT / "targets.json"

MAX_CONC = int(os.getenv("MAX_CONCURRENCY", "8"))
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT_SEC", "12"))
TRIGGER_ON_BOTH = os.getenv("TRIGGER_ON_BOTH", "0") == "1"  # Trueなら在庫あり/なし両方を確定へ

def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

def save_json(p: Path, data):
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)

def blake2s(text: str) -> str:
    return hashlib.blake2s(text.encode("utf-8", errors="ignore")).hexdigest()

def decide_in_stock(html: str, target: dict) -> bool:
    words_in = target.get("in_stock_text_contains") or DEFAULT_IN_WORDS
    words_out = target.get("out_of_stock_text_contains") or DEFAULT_OUT_WORDS
    html_lower = html.lower()
    # 優先：在庫ありワードを1つでも含む
    if any(w.lower() in html_lower for w in words_in):
        return True
    # 明確な売切ワードがあればオフ
    if any(w.lower() in html_lower for w in words_out):
        return False
    # 不明は「前回のまま」に任せるのでここでは False（変化検知はハッシュで拾う）
    return False

async def fetch_one(session: aiohttp.ClientSession, target: dict, hdrs_cache: dict, prev_state: dict):
    url = target["url"]
    name = target.get("name", url)
    cached = hdrs_cache.get(url, {})
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    if et := cached.get("etag"):
        headers["If-None-Match"] = et
    if lm := cached.get("last_modified"):
        headers["If-Modified-Since"] = lm

    try:
        async with session.get(url, headers=headers, timeout=REQUEST_TIMEOUT) as r:
            status = r.status
            # 304: 変更なし → 現状維持
            if status == 304:
                return {"url": url, "name": name, "status": "not_modified"}

            text = await r.text(errors="ignore")
            # ヘッダキャッシュ更新
            new_cache = {}
            etag = r.headers.get("ETag") or r.headers.get("etag")
            lastm = r.headers.get("Last-Modified") or r.headers.get("last-modified")
            if etag: new_cache["etag"] = etag
            if lastm: new_cache["last_modified"] = lastm

            in_stock = decide_in_stock(text, target)
            h = blake2s(text[:200000])  # 先頭20万文字で十分

            # 前回状態
            prev = prev_state.get(url, {})
            prev_stock = prev.get("in_stock")
            prev_hash  = prev.get("hash")

            # 差分判断
            changed = (h != prev_hash) or (in_stock != prev_stock)

            # 次回用に保存
            # （プレーンな在庫判定に加えて、軽量段階ではhashも保存）
            result_state = {"in_stock": in_stock, "hash": h, "name": name, "ts": int(time.time())}
            return {
                "url": url, "name": name, "status": "ok", "http": status,
                "in_stock": in_stock, "hash": h, "changed": changed, "cache_hdrs": new_cache,
            }
    except Exception as e:
        return {"url": url, "name": name, "status": "error", "error": str(e)}

async def main():
    targets = load_json(F_TARGETS, [])
    if not targets:
        print("no targets.json entries")
        return

    hdrs_cache = load_json(F_HDRS, {})
    prev_state = load_json(F_STATE, {})
    needs = []

    conn = aiohttp.TCPConnector(limit_per_host=MAX_CONC, limit=MAX_CONC, ttl_dns_cache=300)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT+2)
    async with aiohttp.ClientSession(connector=conn, timeout=timeout) as session:
        # 軽いジッター（順番分散）
        random.shuffle(targets)
        tasks = [fetch_one(session, t, hdrs_cache, prev_state) for t in targets]
        results = await asyncio.gather(*tasks)

    # 収集＆保存
    new_state = dict(prev_state)
    new_hdrs  = dict(hdrs_cache)

    for res in results:
        url = res["url"]
        if res["status"] == "ok":
            # 状態更新
            new_state[url] = {"in_stock": res["in_stock"], "hash": res["hash"], "name": res["name"], "ts": int(time.time())}
            if res.get("cache_hdrs"):
                new_hdrs[url] = {**new_hdrs.get(url, {}), **res["cache_hdrs"]}
            # 変化があれば確定チェックへ
            prev = prev_state.get(url, {})
            prev_stock = prev.get("in_stock")
            now_stock = res["in_stock"]
            if res["changed"]:
                # 既定：在庫あり化のみトリガ。両方トリガしたい場合は env TRIGGER_ON_BOTH=1
                if (now_stock and not prev_stock) or TRIGGER_ON_BOTH:
                    needs.append({"url": url, "name": res["name"]})
        elif res["status"] == "not_modified":
            # 変化無し → 何もしない
            pass
        else:
            # errorはログだけ（必要なら後で通知）
            print(f"[error] {res['name']}: {res.get('error')}")

    # ファイル反映
    save_json(F_STATE, new_state)
    save_json(F_HDRS, new_hdrs)
    if needs:
        # 既存needsに追記（重複は除外）
        old = load_json(F_NEED, [])
        before = {(x["url"], x.get("name")) for x in old}
        for n in needs:
            if (n["url"], n.get("name")) not in before:
                old.append(n)
        save_json(F_NEED, old)
        print(f"[needs_confirm] {len(needs)} target(s) queued.")
    else:
        # 変化なし → 空ファイルは残してOK（サイズ0にしておく）
        F_NEED.write_text("", encoding="utf-8")

if __name__ == "__main__":
    asyncio.run(main())
