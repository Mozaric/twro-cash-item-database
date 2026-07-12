// Client-side search over normalized items.json + notices.json.
// Both files are fetched, then joined on notice_id before searching.
// No backend: files are served directly from GitHub Pages.
const ITEMS_URL = "data/items.json";
const NOTICES_URL = "data/notices.json";
const MAX_RESULTS = 100;

const form = document.getElementById("search-form");
const input = document.getElementById("search-keyword");
const useRegexCheckbox = document.getElementById("use-regex");
const statusEl = document.getElementById("status");
const table = document.getElementById("result-table");
const tbody = document.getElementById("result-body");

let dataPromise = null;

function loadData() {
  if (!dataPromise) {
    dataPromise = Promise.all([
      fetch(ITEMS_URL).then((res) => {
        if (!res.ok) throw new Error(`資料檔案載入失敗 (HTTP ${res.status})`);
        return res.json();
      }),
      fetch(NOTICES_URL).then((res) => {
        if (!res.ok) throw new Error(`資料檔案載入失敗 (HTTP ${res.status})`);
        return res.json();
      }),
    ]).then(([items, notices]) => {
      const noticeMap = new Map(notices.map((n) => [n.notice_id, n]));
      return items.map((item) => {
        const notice = noticeMap.get(item.notice_id) || {};
        return {
          item_name: item.item_name,
          probability: item.probability,
          acquire_condition: item.acquire_condition,
          notice_id: item.notice_id,
          channel_type: notice.channel_type,
          channel_name: notice.channel_name,
          publish_date: notice.publish_date,
          source_url: notice.source_url,
        };
      });
    });
  }
  return dataPromise;
}

function formatProbabilityOrCondition(record) {
  if (record.channel_type === "消費禮") {
    return record.acquire_condition ? `不適用（${record.acquire_condition}）` : "不適用";
  }
  return record.probability || "不明";
}

function renderResults(matches, totalCount) {
  tbody.innerHTML = "";
  for (const record of matches) {
    const row = document.createElement("tr");

    const itemNameCell = document.createElement("td");
    itemNameCell.textContent = record.item_name;
    row.appendChild(itemNameCell);

    const channelTypeCell = document.createElement("td");
    channelTypeCell.textContent = record.channel_type;
    row.appendChild(channelTypeCell);

    const channelNameCell = document.createElement("td");
    channelNameCell.textContent = record.channel_name;
    row.appendChild(channelNameCell);

    const probCell = document.createElement("td");
    probCell.textContent = formatProbabilityOrCondition(record);
    row.appendChild(probCell);

    const publishDateCell = document.createElement("td");
    publishDateCell.textContent = record.publish_date || "未知";
    row.appendChild(publishDateCell);

    const sourceCell = document.createElement("td");
    const link = document.createElement("a");
    link.href = record.source_url;
    link.textContent = "查看公告";
    link.target = "_blank";
    link.rel = "noopener";
    sourceCell.appendChild(link);
    row.appendChild(sourceCell);

    tbody.appendChild(row);
  }

  table.hidden = matches.length === 0;

  if (totalCount === 0) {
    statusEl.textContent = "查無符合的道具記錄。";
  } else if (totalCount > MAX_RESULTS) {
    statusEl.innerHTML = `找到 ${totalCount} 筆記錄，<span id="truncate-notice">結果過多，僅顯示最新 ${MAX_RESULTS} 筆</span>。`;
  } else {
    statusEl.textContent = `找到 ${totalCount} 筆記錄。`;
  }
}

function showError(message) {
  statusEl.textContent = message;
  table.hidden = true;
}

// publish_date (公告發布日期) 新到舊排序；缺值排最後
function byPublishDateDesc(a, b) {
  if (!a.publish_date) return 1;
  if (!b.publish_date) return -1;
  return b.publish_date.localeCompare(a.publish_date);
}

// 預設「包含比對」(子字串)；勾選「使用正規表示式」後改用 RegExp 比對。
// 兩者皆大小寫不敏感。回傳 null 代表關鍵字/正規表示式不合法，呼叫端應顯示錯誤訊息。
function buildMatcher(keyword, useRegex) {
  if (!useRegex) {
    const lower = keyword.toLowerCase();
    return (itemName) => itemName.toLowerCase().includes(lower);
  }
  let regex;
  try {
    regex = new RegExp(keyword, "i");
  } catch (err) {
    return null;
  }
  return (itemName) => regex.test(itemName);
}

function search(keyword, useRegex) {
  const matcher = buildMatcher(keyword, useRegex);
  if (!matcher) {
    showError("正規表示式格式錯誤，請修改後再試一次。");
    return;
  }

  statusEl.textContent = "查詢中...";
  loadData()
    .then((records) => {
      const matches = records
        .filter((r) => matcher(r.item_name))
        .sort(byPublishDateDesc);
      renderResults(matches.slice(0, MAX_RESULTS), matches.length);
    })
    .catch((err) => {
      showError(`查詢失敗：${err.message}`);
    });
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const keyword = input.value.trim();
  if (keyword) {
    search(keyword, useRegexCheckbox.checked);
  }
});
