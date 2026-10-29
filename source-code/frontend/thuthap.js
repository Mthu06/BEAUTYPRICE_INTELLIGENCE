/* thuthap.js - gọi công cụ thu thập đa nguồn từ website + lịch tự động (chỉ quản trị viên) */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const esc = BP.escapeHtml;
    const STATUS = {
        success: ["badge-good", "Thành công"], partial: ["badge-warn", "Một phần"], blocked: ["badge-bad", "Bị chặn"],
        failed: ["badge-bad", "Lỗi"], stopped: ["badge-warn", "Đã dừng"], skipped: ["badge-warn", "Bỏ qua"]
    };
    // Mẫu nhanh: chỉ đổi lượng dữ liệu, giữ nguyên nguồn/danh mục đang chọn
    const PRESETS = {
        test: { max_pages: 1, reviews: false, review_products: 20, review_pages: 1 },
        normal: { max_pages: 3, reviews: true, review_products: 50, review_pages: 2 },
        full: { max_pages: 0, reviews: true, review_products: 0, review_pages: 0 }
    };
    const NUMBER_FIELDS = { max_pages: "maxPages", review_pages: "reviewPages", review_products: "reviewProducts", delay: "delay" };
    let timer = null;
    let loaded = false;
    let supported = {};

    const statusBadge = (status) => {
        const [cls, label] = STATUS[status] || ["", status || "—"];
        return `<span class="badge ${cls}">${esc(label)}</span>`;
    };

    function readOptions() {
        const checked = (box) => [...$(box).querySelectorAll("input:checked")].map((i) => i.value);
        const opts = {
            sources: checked("sourceList"), categories: checked("categoryList"), reviews: $("optReviews").checked,
            review_sources: checked("reviewSourceList"),
            add_new_products: $("optNewProducts").checked, add_new_reviews: $("optNewReviews").checked
        };
        Object.entries(NUMBER_FIELDS).forEach(([key, id]) => { opts[key] = Number($(id).value); });
        return opts;
    }

    function setNumbers(opts) {
        Object.entries(NUMBER_FIELDS).forEach(([key, id]) => { if (opts[key] !== undefined) $(id).value = String(opts[key]); });
        if (opts.reviews !== undefined) $("optReviews").checked = !!opts.reviews;
        updateEstimate();
    }

    const minutes = (seconds) => seconds < 90 ? `${Math.max(1, Math.round(seconds))} giây` : `${BP.formatNumber(seconds / 60, "—", seconds < 600 ? 1 : 0)} phút`;

    /** Mô tả ngắn một bộ tùy chọn, dùng cho lịch. */
    function describe(o) {
        const all = (n, unit) => n ? `${BP.formatNumber(n)} ${unit}` : `toàn bộ ${unit}`;
        return `${o.sources.length} nguồn · ${o.categories.length} danh mục · ${all(o.max_pages, "trang")}/danh mục · giãn cách ${BP.formatNumber(o.delay, "—", 1)} giây`
            + (o.reviews ? ` · review ${(o.review_sources || []).join(", ")}: ${o.review_products ? BP.formatNumber(o.review_products) : "tất cả"} sản phẩm/nguồn × ${all(o.review_pages, "trang")}` : " · không lấy review")
            + (o.add_new_products ? " · thêm sản phẩm mới" : "");
    }

    /** Ước tính số yêu cầu HTTP và thời gian (mỗi yêu cầu chờ ít nhất `delay` giây). */
    function updateEstimate() {
        const o = readOptions();
        const crawlable = o.sources.filter((s) => supported[s]).length;
        const unknown = !o.max_pages && o.categories.length && crawlable || o.reviews && (!o.review_products || !o.review_pages);
        let requests = crawlable * o.categories.length * (o.max_pages || 1) + o.sources.length;
        if (o.reviews) requests += o.review_sources.length * (o.review_products || 700) * (o.review_pages || 1) + (o.review_sources.includes("cocolux") ? 25 : 0);
        const delay = Math.max(1, o.delay || 1);
        $("estimate").innerHTML = `${BP.icon("info")}<span>Ước tính ${unknown ? "ít nhất" : "tối đa"} <b>~${BP.formatNumber(requests)} yêu cầu</b>, `
            + `khoảng <b>${unknown ? "từ " : ""}${minutes(requests * delay)}</b>${unknown ? " (chọn “toàn bộ / tất cả” nên tùy dữ liệu thực tế, có thể rất lâu)" : ""}.`
            + " Có thể bấm Dừng bất cứ lúc nào, phần đã thu được vẫn được lưu.</span>";
    }

    function fillOptions(opts) {
        document.querySelectorAll("#sourceList input").forEach((i) => { i.checked = opts.sources.includes(i.value); });
        document.querySelectorAll("#categoryList input").forEach((i) => { i.checked = opts.categories.includes(i.value); });
        document.querySelectorAll("#reviewSourceList input").forEach((i) => { i.checked = (opts.review_sources || []).includes(i.value); });
        $("optNewProducts").checked = !!opts.add_new_products;
        $("optNewReviews").checked = !!opts.add_new_reviews;
        setNumbers(opts);
    }

    function renderChoices(data) {
        supported = Object.fromEntries(data.sources.map((s) => [s.key, s.supported]));
        Object.entries(data.limits || {}).forEach(([key, [low, high]]) => {
            if (NUMBER_FIELDS[key]) Object.assign($(NUMBER_FIELDS[key]), { min: low, max: high });
        });
        $("sourceList").innerHTML = data.sources.map((s) => `<label class="${s.supported ? "" : "tt-disabled"}" title="${s.supported ? "" : "Website chặn bot: chỉ kiểm tra truy cập"}">
            <input type="checkbox" value="${esc(s.key)}"><span class="dot r-${esc(s.retailer_id)}"></span>${esc(s.label)}${s.supported ? "" : " (chỉ kiểm tra)"}</label>`).join("");
        $("categoryList").innerHTML = data.categories.map((c) => `<label><input type="checkbox" value="${esc(c.key)}">${esc(c.label)}</label>`).join("");
        $("reviewSourceList").innerHTML = (data.review_sources || []).map((s) => `<label><input type="checkbox" value="${esc(s.key)}"><span class="dot r-${esc(s.key)}"></span>${esc(s.label)}</label>`).join("");
        fillOptions({ ...data.defaults, ...data.schedule?.options });
    }

    function renderJob(job) {
        const running = !!job.running;
        $("startBtn").disabled = running;
        $("stopBtn").hidden = !running;
        $("kpiStatus").textContent = running ? "Đang chạy" : "Sẵn sàng";
        $("kpiStatusSub").textContent = running ? `${job.triggered_by} · từ ${BP.formatDate(job.started_at, true)}` : "Có thể chạy thu thập";
        $("jobBadge").innerHTML = running ? '<span class="badge badge-info">Đang chạy…</span>' : job.summary ? statusBadge(job.summary.status) : job.error ? statusBadge("failed") : "";
        if (job.started_at) {
            $("jobInfo").textContent = `${job.triggered_by || ""} · bắt đầu ${BP.formatDate(job.started_at, true)}`
                + (job.finished_at ? ` · kết thúc ${BP.formatDate(job.finished_at, true)}` : "");
        }
        const log = $("jobLog");
        const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
        log.textContent = job.log?.length ? job.log.join("\n") : "—";
        if (atBottom) log.scrollTop = log.scrollHeight;
        const s = job.summary;
        $("jobSummary").innerHTML = s ? [
            ["Bản ghi giá", s.records], ["+ Snapshot giá", s.new_snapshots], ["+ Sản phẩm mới", s.new_products],
            ["Review thu được", s.reviews_found], ["+ Review mới", s.reviews_added], ["Review bổ sung tên", s.reviews_named],
            ["Review nối biến thể", s.reviews_linked], ["Yêu cầu HTTP", s.requests]
        ].map(([label, value]) => `<div class="stat-tile"><div class="label">${label}</div><div class="value">${BP.formatNumber(value)}</div></div>`).join("")
            : job.error ? BP.stateHtml(job.error, "error") : "";
    }

    function renderSchedule(schedule, fillInputs) {
        const hours = schedule.interval_hours || 24;
        const inDays = hours >= 24 && hours % 24 === 0;
        if (fillInputs) {  // không ghi đè khi đang sửa (trang tự làm mới mỗi 2 giây lúc đang chạy)
            $("scheduleEnabled").checked = !!schedule.enabled;
            $("scheduleEvery").value = String(inDays ? hours / 24 : hours);
            $("scheduleUnit").value = inDays ? "24" : "1";
            $("scheduleUnit").dispatchEvent(new Event("change"));
            $("scheduleFirst").value = "";
        }
        $("scheduleOptions").textContent = schedule.options ? `Lịch đang dùng: ${describe(schedule.options)}.` : "";
        $("kpiSchedule").textContent = schedule.enabled ? "Đang bật" : "Đang tắt";
        $("kpiScheduleSub").textContent = schedule.enabled
            ? `Lần tới: ${BP.formatDate(schedule.next_run_at, true)} · mỗi ${inDays ? `${BP.formatNumber(hours / 24)} ngày` : `${BP.formatNumber(hours, "—", 1)} giờ`}`
            : "Chỉ chạy khi bấm thủ công";
        $("scheduleInfo").textContent = schedule.last_run_at ? `Lần tự động gần nhất: ${BP.formatDate(schedule.last_run_at, true)}` : "";
    }

    function renderHistory(history) {
        const last = history[0];
        $("kpiLast").textContent = last ? BP.formatDate(last.started_at) : "Chưa có";
        $("kpiLastSub").textContent = last ? `${BP.formatNumber(last.records)} bản ghi · +${BP.formatNumber(last.new_snapshots ?? 0)} snapshot` : "—";
        $("historyTable").innerHTML = history.length ? history.map((r) => `<tr>
            <td class="nowrap">${esc(r.run_id)}</td><td class="nowrap">${BP.formatDate(r.started_at, true)}</td>
            <td><div class="tt-retailers">${Object.entries(r.retailers).map(([k, v]) =>
                `<span class="badge ${STATUS[v]?.[0] || ""}" title="${esc(STATUS[v]?.[1] || v)}"><span class="dot r-${esc(k)}"></span>${esc(BP.RETAILER_NAMES[k] || k)}</span>`).join("")}</div></td>
            <td class="num">${BP.formatNumber(r.records)}</td><td class="num">${BP.formatNumber(r.new_snapshots, "—")}</td>
            <td class="num">${BP.formatNumber(r.new_products, "—")}</td><td class="num">${BP.formatNumber(r.reviews_added, "—")}</td>
            <td class="num">${BP.formatNumber(r.reviews_named, "—")}</td></tr>`).join("")
            : `<tr><td colspan="8">${BP.stateHtml("Chưa có lần thu thập nào bằng crawler.")}</td></tr>`;
    }

    async function loadCounts() {
        try {
            const q = await BP.api("/api/data-quality");
            $("kpiData").textContent = `${BP.formatNumber(q.tables.products)} / ${BP.formatNumber(q.tables.price_snapshots)}`;
            $("kpiDataSub").textContent = `${BP.formatNumber(q.tables.reviews)} review trong CSDL`;
        } catch { $("kpiData").textContent = "—"; }
    }

    async function refresh() {
        try {
            const data = await BP.api("/api/crawl");
            renderSchedule(data.schedule, !loaded);
            if (!loaded) { renderChoices(data); loaded = true; }
            renderJob(data.job);
            renderHistory(data.history);
            clearTimeout(timer);
            if (data.job.running) timer = setTimeout(refresh, 2000);
            else if (data.job.summary && !refresh.notified) {
                refresh.notified = true;
                BP.notifyProductsUpdated();
                loadCounts();
            }
        } catch (err) {
            $("pageNotice").innerHTML = `<div class="notice notice-bad">${BP.icon("alert")}<span>${esc(err.message)}</span></div>`;
        }
    }

    async function start(event) {
        event.preventDefault();
        const opts = readOptions();
        if (!opts.sources.length) return BP.toast("Chọn ít nhất 1 nguồn.", "bad");
        if (!opts.categories.length && !opts.reviews) return BP.toast("Chọn ít nhất 1 danh mục hoặc bật thu thập review.", "bad");
        if (opts.reviews && !opts.review_sources.length) return BP.toast("Chọn ít nhất 1 nguồn review.", "bad");
        $("startBtn").disabled = true;
        try {
            const data = await BP.api("/api/crawl/start", { method: "POST", body: opts });
            BP.toast(data.message);
            refresh.notified = false;
            refresh();
        } catch (err) {
            BP.toast(err.message, "bad");
            $("startBtn").disabled = false;
        }
    }

    async function stop() {
        try { BP.toast((await BP.api("/api/crawl/stop", { method: "POST" })).message); } catch (err) { BP.toast(err.message, "bad"); }
    }

    async function saveSchedule() {
        if (!$("crawlForm").reportValidity()) return;
        const every = $("scheduleEvery");
        if (!every.reportValidity()) return;
        const body = {
            enabled: $("scheduleEnabled").checked, interval_hours: Number(every.value) * Number($("scheduleUnit").value),
            first_run_at: $("scheduleFirst").value || null, options: readOptions()
        };
        try {
            const data = await BP.api("/api/crawl/schedule", { method: "PUT", body });
            BP.toast(data.message);
            renderSchedule(data.schedule, true);
        } catch (err) { BP.toast(err.message, "bad"); }
    }

    document.addEventListener("DOMContentLoaded", () => {
        $("reloadBtn").innerHTML = `${BP.icon("refresh")}Tải lại`;
        $("startBtn").innerHTML = `${BP.icon("download")}Chạy thu thập ngay`;
        $("stopBtn").innerHTML = `${BP.icon("x")}Dừng`;
        $("saveSchedule").innerHTML = `${BP.icon("check")}Lưu lịch`;
        [["icStatus", "refresh"], ["icLast", "database"], ["icSchedule", "layers"], ["icData", "box"]].forEach(([id, name]) => { $(id).innerHTML = BP.icon(name); });
        $("formHint").textContent = "Mặc định chỉ cập nhật giá cho sản phẩm đã có.";
        if (!BP.isAdmin()) {
            $("pageNotice").innerHTML = `<div class="notice notice-warn">${BP.icon("alert")}<span>Chức năng thu thập dữ liệu chỉ dành cho quản trị viên.</span></div>`;
            $("startBtn").disabled = true;
            return;
        }
        $("crawlForm").addEventListener("submit", start);
        $("crawlForm").addEventListener("input", updateEstimate);
        $("crawlForm").addEventListener("change", updateEstimate);
        document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => setNumbers(PRESETS[b.dataset.preset])));
        const syncEveryMax = () => { $("scheduleEvery").max = $("scheduleUnit").value === "24" ? 30 : 720; };
        $("scheduleUnit").addEventListener("change", syncEveryMax);
        syncEveryMax();
        $("stopBtn").addEventListener("click", stop);
        $("saveSchedule").addEventListener("click", saveSchedule);
        $("reloadBtn").addEventListener("click", () => { refresh(); loadCounts(); });
        refresh();
        loadCounts();
    });
})();
