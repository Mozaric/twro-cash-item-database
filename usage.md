# 程式使用說明

RO 道具取得管道爬蟲 + 純前端查詢介面。資料正規化為兩個檔案，以 `notice_id` 連結：
- `docs/data/items.json`：每個道具一筆（`notice_id`、`item_name`、`probability`、`acquire_condition`、`scraped_at`）。
- `docs/data/notices.json`：每篇公告一筆（`notice_id`、`notice_title`、`source_url`、`channel_type`、`channel_name`、`period_start`、`period_end`、`publish_date`、`analyzed_at`）。

## 安裝

```bash
# Python 3.9+，建議用虛擬環境
pip install -r requirements.txt        # requests, beautifulsoup4, selenium
pip install -r requirements-dev.txt    # pytest（執行測試用）
```

- 轉蛋頁需要 JS 渲染，會用到 **headless Chrome + chromedriver**（Selenium 自動管理；環境需可執行 Chrome）。
- 消費禮頁只用靜態 HTML，不需要瀏覽器。

## 執行（爬蟲）

```bash
# 1) 手動分析指定公告（強制重新分析，不論是否已分析過都會覆寫）
#    可混用純數字 id 或完整網址，可一次多筆
python -m scraper.cli 218484 218485 --output docs/data/items.json --notices-output docs/data/notices.json

# 2) 自動探索新公告（會跳過 notices.json 裡已分析過的 notice_id）
#    預設關鍵字：轉蛋、消費、維護開機公告
python -m scraper.cli --discover --output docs/data/items.json --notices-output docs/data/notices.json

# 自訂搜尋關鍵字（可重複）／指定公告分類
python -m scraper.cli --discover --search-word 轉蛋 --search-word 消費 --catalog 0
```

- 預設輸出路徑就是 `docs/data/items.json` 與 `docs/data/notices.json`，上面的 `--output`/`--notices-output` 可省略。
- `--discover` 全量探索實測約 1–3 小時（已知且接受的耗時）。
- 漸進式存檔：每處理完一筆候選立即寫檔，中途中斷不會丟失已處理結果。
- 回傳碼：全部成功為 0；手動輸入有任何一筆解析不到道具、或任何候選拋例外，為 1。

## 執行（前端查詢介面）

`docs/` 是純前端靜態網站，直接用任何靜態伺服器開即可（GitHub Pages 或本機）：

```bash
cd docs && python -m http.server 8000
# 瀏覽器開 http://127.0.0.1:8000/index.html   （道具查詢）
#           http://127.0.0.1:8000/sources.html （資料來源清單 / QA）
```

- 查詢頁：輸入關鍵字比對道具名稱（預設子字串、可勾選正規表示式），結果以 `notice_id` join `notices.json` 顯示管道類型／活動名稱／公告發布日期／來源公告，依公告發布日期新到舊排序。
- 資料來源清單頁：列出所有 `channel_type !== '無'` 的公告，點活動名稱（`#notice=<notice_id>`）進入該公告的完整道具清單。

## 執行測試

```bash
cd workspace && python -m pytest tests/ -q
# 88 passed
```

## 輸入輸出範例

輸入：`python -m scraper.cli 218485`

`docs/data/items.json`（每筆只含道具欄位）：
```json
[
  {
    "notice_id": 218485,
    "item_name": "天使之賜福 10等級卷軸[轉蛋專用]",
    "probability": "100.000%",
    "acquire_condition": "",
    "scraped_at": "2026-06-27T00:00:00+00:00"
  }
]
```

`docs/data/notices.json`（每篇公告一筆 metadata）：
```json
[
  {
    "notice_id": 218485,
    "notice_title": "2026/06/16(二)維護開機公告(06/16 15:00更新)",
    "source_url": "https://ro.gnjoy.com.tw/Notice/Notice_View?id=218485",
    "channel_type": "轉蛋",
    "channel_name": "2026 6月轉蛋Ⅱ",
    "period_start": "2026-06-16 00:00",
    "period_end": "2026-07-01 23:59",
    "publish_date": "2026-06-16 14:10",
    "analyzed_at": "2026-06-27T00:00:00+00:00"
  }
]
```

說明：
- 消費禮道具的 `probability` 為 `null`、`acquire_condition` 帶門檻文字；轉蛋道具反之（`acquire_condition` 為空字串）。
- 重爬同一 `notice_id` 會覆寫兩個檔案中該公告的舊記錄（不產生重複）；若重爬後改判為「無」，items.json 對應道具會被清空、notices.json 的 `channel_type` 更新為「無」。
