# LINE Restock Notifier

らぶぶ等の「再入荷」を検知して、LINEに通知します。デフォルトは Python（requests + BeautifulSoup）で静的HTMLを監視します。

> ※JavaScriptで在庫表示が変わるサイトの場合は、CSSセレクタを工夫するか、クラウド監視（GitHub Actions）で定期的にレンダリング後のHTMLを取得できるようにする必要があります（本テンプレはまず静的HTML対応）。

---

## セットアップ（ローカル）

1) **LINE Notifyのトークン発行**  
   - https://notify-bot.line.me/my/ で「トークンを発行」→ コピーして `.env` に貼り付けます。

2) **Python環境**（任意: venv推奨）  
```bash
python -m venv .venv
source .venv/bin/activate  # Windowsは .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # トークンと設定を埋める
```

3) **監視ターゲットの設定**  
   - `targets.json` に監視したい商品ページを追加します（複数OK）。
   - 主なフィールド：
     - `name`: 商品名（任意名）
     - `url`: 商品ページURL
     - `in_stock_css`: 「在庫あり」を示す要素のCSSセレクタ（どちらかが一致すれば在庫あり）
     - `in_stock_text_contains`: 要素内テキストにこの文言が含まれていれば在庫あり（例: "在庫あり", "カートに入れる" 等）
     - `out_of_stock_css` / `out_of_stock_text_contains`: 「売り切れ」判定用（任意）

4) **動作確認**  
```bash
python check_stock.py
```
   - 変更検知（売り切れ→在庫あり 等）が起きた時のみLINE通知します。
   - 過去状態は `state.json` に保存されます。

---

## スケジュール実行（3通り）

### A) ローカル（cron）
```bash
crontab -e
# 5分おきに実行（例）
*/5 * * * * /usr/bin/bash -lc 'cd /path/to/lovebu_line_restock_notifier && . .venv/bin/activate && python check_stock.py >> cron.log 2>&1'
```

### B) GitHub Actions（無料・おすすめ）
1. このフォルダをGitHubにpush  
2. `Settings > Secrets and variables > Actions > New repository secret` で `LINE_NOTIFY_TOKEN` を登録  
3. `.github/workflows/check.yml` のスケジュール（`cron`）を調整  
   - 毎5分: `*/5 * * * *`

### C) Docker（任意）
```bash
docker build -t line-restock .
docker run -e LINE_NOTIFY_TOKEN=YOUR_TOKEN -v $(pwd)/:/app line-restock
```

---

## ヒント（CSSの調べ方）

- Chromeで商品ページを開き、在庫表示（例:「在庫あり」「カートに入れる」「SOLD OUT」等）を右クリック → **検証**。
- 該当要素を選択し、右クリック → **Copy > Copy selector** でCSSセレクタを取得し、`targets.json` に貼る。
- サイトによっては、在庫ボタンが `<button disabled>` で表現されてる場合もあります。その場合は `in_stock_css` をボタンにして `in_stock_text_contains` を省略する、または逆に `out_of_stock_css` + `disabled` 判定を使う等、柔軟に調整してください。

---

## 注意
- 利用規約・robots.txt・法令を遵守してください。
- 激しいアクセスは避け、`interval_seconds` を十分に長くしましょう（GitHub Actionsなら5分以上）。
- 商用規模の監視は公式APIやWebhooksが用意されていないかをまず確認してください。



## LINE Notify 終了に伴う移行（Messaging API）

このテンプレは **LINE Messaging API** を利用して通知します。使う値：

- **LINE_CHANNEL_ACCESS_TOKEN**（Messaging API チャネルの「Long-lived」トークン）
- **LINE_TO_USER_ID**（開発者自身のユーザーID。LINE Developers Console > 該当チャネル > Basic settings > Your user ID）

> ※ あなた以外のユーザーに送る場合は、Botを「友だち追加」してもらい、Webhook 経由で `userId` を取得するか、followers APIで取得します。

### 取得手順（超要約）
1. [LINE Developers](https://developers.line.biz/) で Provider を作成し **Messaging API チャネル**を作る  
2. チャネルの **Messaging API タブ**から **Long-lived Channel Access Token** を発行 → `.env` または GitHub Secrets へ  
3. **Basic settings** の **Your user ID** を控える（自分にpushする場合）  
4. `.env` に `LINE_CHANNEL_ACCESS_TOKEN` と `LINE_TO_USER_ID` をセット
