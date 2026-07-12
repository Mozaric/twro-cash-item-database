// QA source-list page: reads notices.json for the list and items.json for
// per-notice detail, joining on notice_id rather than grouping items.json
// by source_url (which would duplicate all notice-level fields per item).
(function () {
  var resultEl = document.getElementById("result");
  var notices = [];         // all notices from notices.json, sorted newest-first
  var itemsByNoticeId = {}; // items.json rows indexed by notice_id

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function formatProbabilityOrCondition(item, channelType) {
    if (channelType === "消費禮") {
      return item.acquire_condition ? "不適用（" + item.acquire_condition + "）" : "不適用";
    }
    return item.probability || "不明";
  }

  function renderList() {
    var active = notices.filter(function (n) { return n.channel_type !== "無"; });
    if (active.length === 0) {
      resultEl.innerHTML = '<p class="empty">尚無已爬取的資料。</p>';
      return;
    }

    var rows = active.map(function (notice) {
      return "<tr>" +
        '<td><a href="#notice=' + notice.notice_id + '">' + escapeHtml(notice.channel_name) + "</a></td>" +
        "<td>" + escapeHtml(notice.channel_type) + "</td>" +
        "<td>" + escapeHtml(notice.publish_date) + "</td>" +
        "<td>" + escapeHtml(notice.period_start) + " ~ " + escapeHtml(notice.period_end) + "</td>" +
        '<td><a href="' + escapeHtml(notice.source_url) + '" target="_blank" rel="noopener">公告連結</a></td>' +
        "</tr>";
    }).join("");

    resultEl.innerHTML =
      "<table><thead><tr>" +
      "<th>活動名稱</th><th>管道類型</th><th>公告發布日期</th><th>活動期間</th><th>原始公告</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table>";
  }

  function renderDetail(noticeId) {
    var notice = notices.find(function (n) { return n.notice_id === noticeId; });
    if (!notice) { renderList(); return; }

    var items = itemsByNoticeId[noticeId] || [];
    var rows = items.map(function (item) {
      return "<tr>" +
        "<td>" + escapeHtml(item.item_name) + "</td>" +
        "<td>" + escapeHtml(formatProbabilityOrCondition(item, notice.channel_type)) + "</td>" +
        "<td>" + escapeHtml(item.acquire_condition) + "</td>" +
        "</tr>";
    }).join("");

    resultEl.innerHTML =
      '<a class="back-link" href="#">&larr; 返回清單</a>' +
      "<h2>" + escapeHtml(notice.channel_name) + "</h2>" +
      "<p>管道類型：" + escapeHtml(notice.channel_type) +
      "　公告發布日期：" + escapeHtml(notice.publish_date) +
      "　活動期間：" + escapeHtml(notice.period_start) + " ~ " + escapeHtml(notice.period_end) +
      '　<a href="' + escapeHtml(notice.source_url) + '" target="_blank" rel="noopener">原始公告連結</a></p>' +
      "<table><thead><tr><th>道具名稱</th><th>機率</th><th>取得條件</th></tr></thead><tbody>" +
      rows + "</tbody></table>";
  }

  function route() {
    var hash = location.hash;
    var match = hash.match(/^#notice=(\d+)$/);
    if (match) {
      renderDetail(Number(match[1]));
    } else {
      renderList();
    }
  }

  Promise.all([
    fetch("data/notices.json").then(function (r) { return r.json(); }),
    fetch("data/items.json").then(function (r) { return r.json(); }),
  ]).then(function (results) {
    notices = results[0];
    notices.sort(function (a, b) {
      if (!a.publish_date) return 1;
      if (!b.publish_date) return -1;
      return b.publish_date.localeCompare(a.publish_date);
    });
    var items = results[1];
    items.forEach(function (item) {
      var id = item.notice_id;
      if (!itemsByNoticeId[id]) itemsByNoticeId[id] = [];
      itemsByNoticeId[id].push(item);
    });
    route();
  }).catch(function (err) {
    resultEl.innerHTML = '<p class="empty">資料載入失敗：' + escapeHtml(err.message) + "</p>";
  });

  window.addEventListener("hashchange", route);
})();
