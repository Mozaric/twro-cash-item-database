# RO 道具取得管道查詢

爬取 RO 仙境傳說官網公告（轉蛋 / 消費禮），把道具取得管道整理成可查詢的靜態網站。

- **線上查詢**：`https://mozaric.github.io/twro-cash-item-database/`
- 資料正規化為兩個檔案，以 `notice_id` 連結：
  - `docs/data/items.json`：每個道具一筆
  - `docs/data/notices.json`：每篇公告一筆（metadata）

## 專案結構

```
docs/            ← GitHub Pages 服務此資料夾（純前端網站）
  index.html       道具查詢頁
  sources.html     資料來源清單（QA）
  app.js / sources.js / style.css
  data/            網站讀取的資料（要一起 commit）
    items.json
    notices.json
  .nojekyll        關閉 Jekyll 處理
scraper/         Python 爬蟲（產生 data/*.json，不會被網站服務）
tests/           單元測試
requirements.txt / requirements-dev.txt
usage.md         詳細安裝／執行／範例說明
```

## 快速開始

安裝與執行方式詳見 [usage.md](usage.md)。

```bash
pip install -r requirements.txt
# 自動探索並更新資料
python -m scraper.cli --discover
# 本機預覽網站
cd docs && python -m http.server 8000   # 開 http://127.0.0.1:8000/
```

## 部署到 GitHub Pages

1. 把整個專案推到 GitHub。
2. Repo → **Settings → Pages → Build and deployment**：
   - Source：**Deploy from a branch**
   - Branch：`main`，資料夾選 **`/docs`**，Save。
3. 等一兩分鐘，網站會出現在 `https://mozaric.github.io/twro-cash-item-database/`。
4. 之後每次重跑爬蟲、把更新後的 `docs/data/*.json` commit & push，網站就會自動更新。
