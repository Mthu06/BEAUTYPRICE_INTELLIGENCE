/* tracuu.js - Tra cứu, lọc, xem chi tiết và quản lý sản phẩm (thêm/sửa/xóa chỉ dành cho Admin). Cần common.js (window.BP). */
(function () {
    "use strict";
    if (!BP.getSession()) return; // common.js đang chuyển về trang đăng nhập

    const PAGE_SIZE = 50, REVIEW_PAGE = 8;
    const $ = (id) => document.getElementById(id);
    const esc = BP.escapeHtml, num = BP.toNumber;
    const FILTERS = ["retailerFilter", "categoryFilter", "brandFilter", "priceFilter", "discountFilter"];
    const NO_CATEGORY = "__none";
    const TYPE_LABELS = { single: "Sản phẩm lẻ", bundle: "Combo", multi_pack: "Gói nhiều món", unknown: "Chưa xác định" };
    const SORTS = {
        name: (a, b) => (a.p.product_name || "").localeCompare(b.p.product_name || "", "vi"),
        priceAsc: (a, b) => (a.price ?? Infinity) - (b.price ?? Infinity),
        priceDesc: (a, b) => (b.price ?? -1) - (a.price ?? -1),
        discount: (a, b) => (b.discount ?? -1) - (a.discount ?? -1),
        rating: (a, b) => (b.rating ?? -1) - (a.rating ?? -1) || (num(b.p.review_count) ?? 0) - (num(a.p.review_count) ?? 0)
    };

    let rows = [], rowById = new Map(), filtered = [];
    let reviewsByProduct = null;       // Map product_id -> reviews; null = chưa tải được
    let retailers = [], categories = [];
    let page = 1, loadSeq = 0, detailSeq = 0;
    let detail = null;                 // { id, reviews, shown }
    let editing = null, deleting = null, busy = false;

    // ---------------------------------------------------------------- tiện ích
    const brandKey = (v) => BP.normalizeText(v).replace(/[^a-z0-9]/g, "");
    const reviewStar = (r) => Math.min(5, Math.max(1, Math.floor(num(r.rating) || 0))); // 4,5 sao -> nhóm 4 sao
    const discountOf = (price, listed) => (listed > 0 && price > 0 && listed >= price ? Math.round((listed - price) / listed * 10000) / 100 : null);
    const errorText = (err) => (err.status === 403 ? "Bạn không có quyền thực hiện thao tác này (cần tài khoản Admin)." : err.message);
    const setNotice = (id, message) => { $(id).innerHTML = message ? BP.icon("alert") + `<span>${esc(message)}</span>` : ""; $(id).hidden = !message; };

    /** ★ đúng cả nửa sao (nửa sao tô bằng CSS). */
    function starsHtml(rating) {
        const r = Math.round((num(rating) || 0) * 2) / 2; // làm tròn tới nửa sao
        return `<span class="tc-stars" aria-label="${BP.formatRating(r)} sao">` + [1, 2, 3, 4, 5].map((i) =>
            `<i class="${r >= i ? "on" : r >= i - 0.5 ? "half" : ""}">★</i>`).join("") + "</span>";
    }

    function ratingHtml(p) {
        const rating = num(p.rating), count = num(p.review_count);
        if (!(rating > 0)) return '<span class="muted">—</span>';
        return `<span class="tc-rating"><b>★</b>${BP.formatRating(rating)}</span>` + (count > 0 ? ` <span class="muted small">(${BP.formatNumber(count)})</span>` : "");
    }

    const retailerHtml = (p) => `<span class="tc-retailer"><span class="dot" data-color="${esc(p.retailer_id)}"></span>${esc(p.source || p.retailer_id || "—")}</span>`;
    /** Tô màu chấm nhà bán lẻ sau khi chèn HTML (không dùng inline style). */
    const paintDots = (root) => root.querySelectorAll(".dot[data-color]").forEach((d) => { d.style.background = BP.retailerColor(d.dataset.color); });

    // ---------------------------------------------------------------- dữ liệu
    function buildRow(p) {
        return {
            p, id: String(p.id),
            search: BP.normalizeText(`${p.product_name} ${p.brand} ${p.category || ""}`),
            brand: brandKey(p.brand),
            price: num(p.current_price_vnd),
            discount: num(p.discount_percent),
            rating: num(p.rating) > 0 ? num(p.rating) : null,
            collected: reviewsByProduct ? (reviewsByProduct.get(String(p.id)) || []).length : null
        };
    }

    function fillSelect(id, pairs, extra = []) {
        const select = $(id), current = select.value, first = select.options[0].outerHTML;
        const options = new Map();
        pairs.forEach(([key, label]) => { if (key && !options.has(key)) options.set(key, String(label).trim()); });
        const sorted = [...options].sort((a, b) => a[1].localeCompare(b[1], "vi")).concat(extra);
        select.innerHTML = first + sorted.map(([k, l]) => `<option value="${esc(k)}">${esc(l)}</option>`).join("");
        select.value = sorted.some(([k]) => k === current) ? current : "";
    }

    async function load() {
        const seq = ++loadSeq;
        if (!rows.length) renderSkeleton();
        const [products, reviews, lookups] = await Promise.allSettled([
            BP.api("/api/products"),
            reviewsByProduct ? null : BP.api("/api/reviews"),
            retailers.length ? null : BP.api("/api/lookups")
        ]);
        // Review/lookups không phụ thuộc lần tải nên giữ lại kể cả khi lần tải này đã cũ.
        if (!reviewsByProduct && reviews.status === "fulfilled" && reviews.value) {
            reviewsByProduct = new Map();
            for (const r of reviews.value.reviews || []) {
                if (r.product_id == null) continue;
                const key = String(r.product_id);
                if (!reviewsByProduct.has(key)) reviewsByProduct.set(key, []);
                reviewsByProduct.get(key).push(r);
            }
        }
        if (!retailers.length && lookups.status === "fulfilled" && lookups.value) {
            retailers = lookups.value.retailers || [];
            categories = lookups.value.categories || [];
        }
        if (seq !== loadSeq) return; // đã có lần tải mới hơn
        if (products.status === "rejected") {
            if (rows.length) setNotice("noticeBox", `Không cập nhật được danh sách sản phẩm: ${products.reason.message}`);
            else showState(products.reason.message, "error");
            return;
        }
        setNotice("noticeBox", reviewsByProduct ? "" : `Không tải được review đã thu thập (${reviews.reason?.message || "lỗi không xác định"}). Cột "Review thu thập" tạm hiển thị "—".`);
        rows = (products.value.products || []).map(buildRow);
        rowById = new Map(rows.map((r) => [r.id, r]));
        fillSelect("retailerFilter", rows.map((r) => [r.p.retailer_id, r.p.source || r.p.retailer_id]));
        fillSelect("categoryFilter", rows.map((r) => [r.p.category, r.p.category]), rows.some((r) => !r.p.category) ? [[NO_CATEGORY, "Không rõ / nhiều danh mục"]] : []);
        fillSelect("brandFilter", rows.map((r) => [r.brand, r.p.brand]));
        applyFilters(false);
        if (detail && !$("detailModal").hidden && !rowById.has(detail.id)) closeModal("detailModal", true); // đã bị xóa ở tab khác
    }

    // ---------------------------------------------------------------- bảng
    function applyFilters(resetPage = true) {
        const terms = BP.normalizeText($("searchInput").value).split(" ").filter(Boolean);
        const [retailer, category, brand, band, disc] = FILTERS.map((id) => $(id).value);
        filtered = rows.filter((r) =>
            terms.every((t) => r.search.includes(t)) &&
            (!retailer || r.p.retailer_id === retailer) &&
            (!category || (category === NO_CATEGORY ? !r.p.category : r.p.category === category)) &&
            (!brand || r.brand === brand) &&
            (!band || BP.priceBand(r.price) === band) &&
            (!disc || BP.discountBucket(r.discount) === disc));
        const sort = SORTS[$("sortSelect").value] || SORTS.name;
        filtered.sort((a, b) => sort(a, b) || SORTS.name(a, b));
        if (resetPage) page = 1;
        renderPage();
    }

    function showState(message, type) {
        $("tableBody").innerHTML = $("pagination").innerHTML = $("footText").textContent = "";
        $("stateBox").hidden = false;
        $("stateBox").innerHTML = BP.stateHtml(message, type) + (type === "error"
            ? '<div class="tc-retry"><button type="button" class="btn btn-outline btn-sm" data-retry>Thử lại</button></div>' : "");
        if (type === "error") $("summaryText").textContent = "Không tải được dữ liệu";
    }

    function renderSkeleton() {
        $("stateBox").hidden = true;
        $("summaryText").textContent = "Đang tải…";
        const cell = (w) => `<td><span class="skeleton tc-sk ${w}">&nbsp;</span></td>`;
        $("tableBody").innerHTML = `<tr>${cell("w-lg")}${cell("w-md")}${cell("w-sm")}${cell("w-sm")}${cell("w-xs")}${cell("w-sm")}${cell("w-xs")}${cell("w-sm")}</tr>`.repeat(8);
    }

    function renderPage() {
        const total = filtered.length, totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
        page = Math.min(Math.max(1, page), totalPages);
        const start = (page - 1) * PAGE_SIZE, end = Math.min(start + PAGE_SIZE, total), f = BP.formatNumber;
        const summary = total ? `Hiển thị ${f(start + 1)}–${f(end)} / ${f(total)} sản phẩm` : "Không có sản phẩm phù hợp";
        $("summaryText").textContent = summary + (total !== rows.length ? ` (lọc từ ${f(rows.length)})` : "");
        $("footText").textContent = total ? `Trang ${page}/${totalPages}` : "";
        if (!total) return showState(rows.length ? "Không tìm thấy sản phẩm phù hợp với bộ lọc." : "Chưa có sản phẩm nào.", "empty");
        $("stateBox").hidden = true;
        const admin = BP.isAdmin();
        const btn = (action, icon, title, id) => `<button type="button" class="btn btn-ghost btn-icon tc-act${action === "delete" ? " danger" : ""}" data-action="${action}" data-id="${esc(id)}" title="${title}" aria-label="${title}">${BP.icon(icon)}</button>`;
        $("tableBody").innerHTML = filtered.slice(start, end).map(({ p, id, discount, collected }) => {
            const listed = num(p.listed_price_vnd);
            return `<tr>
                <td class="name-cell tc-name"><button type="button" class="tc-link" data-action="view" data-id="${esc(id)}">${esc(p.product_name || "Chưa có tên")}</button>
                    <small>${esc(p.brand || "—")} · ${esc(p.category || "Không rõ danh mục")}</small></td>
                <td class="nowrap tc-ret">${retailerHtml(p)}</td>
                <td class="num nowrap tc-price">${BP.formatVnd(p.current_price_vnd)}</td>
                <td class="num nowrap tc-lp">${listed > 0 ? `<s class="tc-listed">${BP.formatVnd(listed)}</s>` : '<span class="muted">—</span>'}</td>
                <td class="num tc-disc">${discount > 0 ? `<span class="badge badge-bad">−${BP.formatPercent(discount, 0)}</span>` : '<span class="muted">—</span>'}</td>
                <td class="nowrap tc-rate">${ratingHtml(p)}</td>
                <td class="num tc-rev" data-label="Review thu thập: ">${collected === null ? "—" : collected ? BP.formatNumber(collected) : '<span class="muted">0</span>'}</td>
                <td class="tc-act-cell"><div class="tc-actions">${btn("view", "eye", "Xem chi tiết", id)}${admin ? btn("edit", "edit", "Sửa", id) + btn("delete", "trash", "Xóa", id) : ""}</div></td>
            </tr>`;
        }).join("");
        paintDots($("tableBody"));
        BP.renderPagination($("pagination"), page, totalPages, (p) => {
            page = p;
            renderPage();
            $("summaryText").closest(".card").scrollIntoView({ behavior: "smooth", block: "start" });
        });
    }

    function exportCsv() {
        if (!filtered.length) return BP.toast("Không có dữ liệu để xuất.", "bad");
        const header = ["Mã SP", "Tên sản phẩm", "Thương hiệu", "Nhà bán lẻ", "Danh mục", "Giá hiện tại (đ)", "Giá niêm yết (đ)", "% giảm", "Rating website", "Lượt đánh giá website", "Review đã thu thập", "Link", "Thu thập lúc"];
        const data = filtered.map(({ p, collected }) => [p.id, p.product_name, p.brand, p.source, p.category ?? "", p.current_price_vnd ?? "", p.listed_price_vnd ?? "",
            p.discount_percent ?? "", p.rating ?? "", p.review_count ?? "", collected ?? "", BP.safeUrl(p.product_url), p.collected_at ?? ""]);
        BP.downloadCsv(`tra-cuu-san-pham-${new Date().toISOString().slice(0, 10)}.csv`, [header, ...data]);
        BP.toast(`Đã xuất ${BP.formatNumber(filtered.length)} sản phẩm ra CSV.`);
    }

    // ---------------------------------------------------------------- modal chung
    function openModal(id) { $(id).hidden = false; document.body.classList.add("tc-lock"); }
    function closeModal(id, force = false) {
        if (busy && !force) return; // đang lưu/xóa -> không cho đóng
        $(id).hidden = true;
        if (id === "detailModal") { detail = null; detailSeq++; }
        if (!document.querySelector(".modal-overlay:not([hidden])")) document.body.classList.remove("tc-lock");
    }

    /** Khóa modal trong lúc gửi request; thành công -> đóng, toast, tải lại giữ trang. */
    async function runBusy(modalId, button, busyText, errorId, task) {
        const label = button.textContent;
        const lock = (on) => { busy = button.disabled = on; button.textContent = on ? busyText : label; };
        lock(true);
        setNotice(errorId, "");
        try {
            const message = await task();
            lock(false);
            closeModal(modalId);
            BP.toast(message);
            BP.notifyProductsUpdated();
            load(); // load() giữ nguyên trang đang xem
        } catch (err) {
            lock(false);
            setNotice(errorId, errorText(err));
        }
    }

    // ---------------------------------------------------------------- chi tiết
    function openDetail(row) {
        const p = row.p, seq = ++detailSeq, listed = num(p.listed_price_vnd);
        detail = { id: row.id, reviews: reviewsByProduct?.get(row.id) || [], shown: REVIEW_PAGE };
        $("detailTitle").textContent = p.product_name || "Chi tiết sản phẩm";
        $("detailSub").innerHTML = `${esc(p.brand || "—")} · ${retailerHtml(p)}`;
        paintDots($("detailSub"));
        const tile = (label, value, sub = "") => `<div class="stat-tile"><div class="label">${label}</div><div class="value">${value}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
        $("detailTiles").innerHTML = [
            tile("Giá hiện tại", BP.formatVnd(p.current_price_vnd)),
            tile("Giá niêm yết", listed > 0 ? BP.formatVnd(listed) : "—", listed > 0 ? "" : "Không có giá niêm yết"),
            tile("Giảm giá", row.discount > 0 ? `<span class="tc-off">−${BP.formatPercent(row.discount)}</span>` : "—"),
            tile("Rating website", num(p.rating) > 0 ? `<span class="tc-rating"><b>★</b>${BP.formatRating(p.rating)}</span>` : "—",
                num(p.review_count) > 0 ? `${BP.formatNumber(p.review_count)} lượt đánh giá` : "Chưa có lượt đánh giá"),
            tile("Review đã thu thập", reviewsByProduct ? BP.formatNumber(detail.reviews.length) : "—", reviewsByProduct ? "Hasaki / Guardian" : "Không tải được review")
        ].join("");
        renderInfo(p, null);
        $("historyMeta").textContent = $("historyNote").textContent = "";
        setHistoryState("Đang tải lịch sử giá…", "loading");
        $("reviewStar").value = "";
        $("reviewSort").value = "newest";
        renderReviewStats();
        renderReviewList();
        openModal("detailModal");
        $("detailModal").querySelector(".modal-body").scrollTop = 0;

        BP.api(`/api/products/${encodeURIComponent(row.id)}`).then((data) => {
            if (seq !== detailSeq) return; // đã mở sản phẩm khác
            renderInfo(data.product || p, data.categories || []);
            renderHistory(data.history || []);
        }).catch((err) => {
            if (seq === detailSeq) setHistoryState(`Không tải được lịch sử giá: ${err.message}`, "error");
        });
    }

    function renderInfo(p, cats) {
        const size = [num(p.volume_ml) > 0 && `${BP.formatNumber(p.volume_ml, "", 1)} ml`, num(p.weight_g) > 0 && `${BP.formatNumber(p.weight_g, "", 1)} g`,
            num(p.pack_count) > 1 && `${BP.formatNumber(p.pack_count)} món`].filter(Boolean).join(" · ");
        const extra = (cats || []).filter((c) => c !== p.category);
        const url = BP.safeUrl(p.product_url);
        const item = (label, value) => `<dt>${label}</dt><dd>${value}</dd>`;
        $("detailInfo").innerHTML = [
            item("Nhà bán lẻ", retailerHtml(p)),
            item("Thương hiệu", esc(p.brand || "—")),
            item("Danh mục", esc(p.category || (cats && cats.length > 1 ? "Nhiều danh mục" : "Không rõ"))),
            cats === null ? "" : item("Danh mục phụ", extra.length ? extra.map((c) => `<span class="badge">${esc(c)}</span>`).join(" ") : '<span class="muted">—</span>'),
            item("Loại sản phẩm", esc(TYPE_LABELS[p.product_type] || p.product_type || "—") + (Number(p.is_combo) && p.product_type !== "bundle" ? ' <span class="badge badge-info">Combo</span>' : "")),
            size ? item("Dung tích / KL / số món", esc(size)) : "",
            item("Nguồn dữ liệu", p.data_origin === "manual" ? '<span class="badge badge-warn">Nhập tay</span>' : '<span class="badge badge-good">Thu thập tự động</span>'),
            item("Cập nhật lần cuối", BP.formatDate(p.collected_at, true)),
            item("Trang sản phẩm", url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" class="tc-ext">Xem trên website ${BP.icon("external")}</a>` : '<span class="muted">Chưa có link</span>')
        ].join("");
        paintDots($("detailInfo"));
    }

    function setHistoryState(message, type) {
        $("historyState").innerHTML = message ? BP.stateHtml(message, type) : "";
        $("historyState").hidden = !message;
        $("historyBox").hidden = !!message;
    }

    function renderHistory(history) {
        const points = history.filter((h) => num(h.current_price_vnd) > 0);
        if (!points.length) return setHistoryState("Chưa có dữ liệu giá.", "empty");
        setHistoryState("");
        const prices = points.map((h) => num(h.current_price_vnd));
        const hasListed = points.some((h) => num(h.listed_price_vnd) > 0);
        const datasets = [{ label: "Giá hiện tại", data: prices, borderColor: BP.COLORS.series[0], backgroundColor: BP.COLORS.series[0], pointRadius: 4, tension: 0 }];
        if (hasListed) datasets.push({ label: "Giá niêm yết", data: points.map((h) => num(h.listed_price_vnd) || null), borderColor: BP.COLORS.muted,
            backgroundColor: BP.COLORS.muted, borderDash: [6, 4], pointRadius: 3, spanGaps: true });
        BP.chart("historyChart", {
            type: "line",
            data: { labels: points.map((h) => BP.formatDate(h.collected_at, true)), datasets },
            options: {
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { display: hasListed, position: "bottom" },
                    tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${BP.formatVnd(c.parsed.y)}` } }
                },
                scales: { x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 5 } }, y: BP.vndAxis({ grace: "8%" }) }
            }
        });
        const min = Math.min(...prices), max = Math.max(...prices), change = prices[prices.length - 1] - prices[0];
        $("historyMeta").textContent = `${BP.formatNumber(points.length)} lần thu thập`;
        $("historyNote").textContent = points.length === 1
            ? "Mới có 1 lần thu thập — đường giá sẽ hiện khi có thêm lần cập nhật."
            : `Thấp nhất ${BP.formatVnd(min)} · Cao nhất ${BP.formatVnd(max)} · Thay đổi từ lần đầu: ${change === 0 ? "không đổi" : (change > 0 ? "+" : "−") + BP.formatVnd(Math.abs(change))}`;
    }

    function renderReviewStats() {
        const list = detail.reviews, total = list.length;
        $("reviewStar").parentElement.hidden = $("reviewList").parentElement.hidden = !total;
        $("reviewStats").parentElement.classList.toggle("tc-single", !total);
        if (!total) {
            $("reviewStats").innerHTML = `<div class="tc-review-empty">${reviewsByProduct ? "Chưa thu thập được review nào cho sản phẩm này." : "Không tải được dữ liệu review."}</div>`;
            return;
        }
        const counts = [0, 0, 0, 0, 0, 0];
        list.forEach((r) => counts[reviewStar(r)]++);
        const avg = BP.average(list.map((r) => r.rating));
        $("reviewStats").innerHTML = `<div class="tc-avg"><div class="tc-avg-num">${BP.formatNumber(avg, "—", 2)}</div>${starsHtml(avg)}
                <div class="muted small">${BP.formatNumber(total)} review đã thu thập</div></div>
            <div class="bar-list tc-star-bars">${[5, 4, 3, 2, 1].map((s) => `<div class="bar-item"><span class="bar-label">${s} sao</span>
                <div class="bar-track"><div class="bar-fill" style="width:${(counts[s] / total * 100).toFixed(1)}%"></div></div>
                <span class="bar-value">${BP.formatNumber(counts[s])}</span></div>`).join("")}</div>`;
    }

    function renderReviewList() {
        if (!detail) return;
        const star = Number($("reviewStar").value), sort = $("reviewSort").value;
        const time = (r) => BP.parseReviewDate(r.review_date || r.review_date_raw);
        const byDate = (a, b) => time(b) - time(a);
        const list = detail.reviews.filter((r) => !star || reviewStar(r) === star).sort({
            newest: byDate, oldest: (a, b) => time(a) - time(b),
            high: (a, b) => num(b.rating) - num(a.rating) || byDate(a, b), low: (a, b) => num(a.rating) - num(b.rating) || byDate(a, b)
        }[sort]);
        const shown = list.slice(0, detail.shown);
        $("reviewList").innerHTML = shown.length ? shown.map((r) => `<article class="tc-review">
                <div class="tc-reviewer"><span class="avatar tc-reviewer-avatar">${esc((r.reviewer_name || "K").charAt(0).toUpperCase())}</span>
                    <b>${esc(r.reviewer_name || "Khách hàng")}</b></div>
                <div class="tc-review-top">${starsHtml(r.rating)}<b>${BP.formatRating(r.rating)}</b>
                    <span class="muted small">${esc(r.review_date ? BP.formatDate(r.review_date) : r.review_date_raw || "—")}</span>
                    <span class="spacer"></span>
                    ${r.is_bought ? '<span class="badge badge-good">Đã mua hàng</span>' : ""}${r.has_images ? '<span class="badge">Có ảnh</span>' : ""}
                    <span class="badge">${esc(BP.RETAILER_NAMES[r.source] || r.source || "—")}</span></div>
                <p>${esc(r.review_text || "Không có nội dung")}</p></article>`).join("")
            : `<div class="tc-review-empty">${detail.reviews.length ? "Không có review phù hợp với bộ lọc." : "Chưa có review để hiển thị."}</div>`;
        const rest = list.length - shown.length;
        $("reviewMore").hidden = rest <= 0;
        $("reviewMore").textContent = `Xem thêm (${BP.formatNumber(rest)} review)`;
    }

    // ---------------------------------------------------------------- thêm / sửa / xóa
    function updateDiscount() {
        const d = discountOf(num($("fPrice").value), num($("fListed").value));
        $("fDiscount").value = d === null ? "" : BP.formatPercent(d, 2);
    }

    function openForm(row) {
        if (!BP.isAdmin()) return BP.toast("Chỉ tài khoản Admin mới được thêm/sửa sản phẩm.", "bad");
        editing = row;
        const p = row?.p || {};
        const retailerList = retailers.length ? retailers : Object.entries(BP.RETAILER_NAMES).map(([retailer_id, retailer_name]) => ({ retailer_id, retailer_name }));
        const categoryList = categories.length ? categories : [...new Set(rows.map((r) => r.p.category).filter(Boolean))].sort();
        $("fRetailer").innerHTML = '<option value="">— Chọn nhà bán lẻ —</option>' + retailerList.map((r) => `<option value="${esc(r.retailer_id)}">${esc(r.retailer_name)}</option>`).join("");
        $("fCategory").innerHTML = '<option value="">Không rõ</option>' + categoryList.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
        $("formTitle").textContent = row ? "Sửa sản phẩm" : "Thêm sản phẩm";
        $("formSub").textContent = row ? "Chỉ những trường bạn thay đổi mới được gửi lên" : "Nhập thông tin sản phẩm cần quản lý";
        Object.entries({ fName: p.product_name, fBrand: p.brand, fRetailer: p.retailer_id, fCategory: p.category, fUrl: p.product_url,
            fPrice: num(p.current_price_vnd), fListed: num(p.listed_price_vnd) }).forEach(([id, v]) => { $(id).value = v || ""; });
        updateDiscount();
        setNotice("formError", "");
        openModal("formModal");
        $("fName").focus();
    }

    function saveForm(event) {
        event.preventDefault();
        if (busy) return;
        const price = num($("fPrice").value), listed = $("fListed").value.trim() === "" ? null : num($("fListed").value);
        const data = {
            product_name: $("fName").value.trim(), brand: $("fBrand").value.trim(), retailer_id: $("fRetailer").value,
            category: $("fCategory").value, product_url: $("fUrl").value.trim(), current_price_vnd: price, listed_price_vnd: listed
        };
        const invalid = !data.product_name ? "Vui lòng nhập tên sản phẩm."
            : !data.brand ? "Vui lòng nhập thương hiệu."
            : !data.retailer_id ? "Vui lòng chọn nhà bán lẻ."
            : !(price > 0) ? "Giá hiện tại phải lớn hơn 0."
            : listed !== null && !(listed > 0) ? "Giá niêm yết phải lớn hơn 0 (hoặc để trống)."
            : listed !== null && listed < price ? "Giá niêm yết phải lớn hơn hoặc bằng giá hiện tại."
            : data.product_url && !BP.safeUrl(data.product_url) ? "Link sản phẩm phải bắt đầu bằng http:// hoặc https://"
            : "";
        if (invalid) return setNotice("formError", invalid);

        let body = data;
        if (editing) {
            const p = editing.p;
            const old = { product_name: p.product_name || "", brand: p.brand || "", retailer_id: p.retailer_id || "", category: p.category || "",
                product_url: p.product_url || "", current_price_vnd: num(p.current_price_vnd), listed_price_vnd: num(p.listed_price_vnd) > 0 ? num(p.listed_price_vnd) : null };
            body = Object.fromEntries(Object.entries(data).filter(([k, v]) => v !== old[k]));
            if (!Object.keys(body).length) { closeModal("formModal"); return BP.toast("Không có thay đổi nào để lưu."); }
            if ("listed_price_vnd" in body && body.listed_price_vnd === null) body.listed_price_vnd = 0; // backend hiểu 0 = xóa giá niêm yết
        }
        const id = editing?.id;
        runBusy("formModal", $("formSubmit"), id ? "Đang lưu…" : "Đang thêm…", "formError", async () => {
            const res = await BP.api(id ? `/api/products/${encodeURIComponent(id)}` : "/api/products", { method: id ? "PUT" : "POST", body });
            return res.message || (id ? "Đã cập nhật sản phẩm." : "Đã thêm sản phẩm mới.");
        });
    }

    function askDelete(row) {
        if (!BP.isAdmin()) return BP.toast("Tài khoản User không có quyền xóa dữ liệu.", "bad");
        deleting = row;
        $("deleteName").textContent = row.p.product_name || "Chưa có tên";
        setNotice("deleteError", "");
        openModal("deleteModal");
    }

    function confirmDelete() {
        if (!deleting || busy) return;
        const id = deleting.id;
        runBusy("deleteModal", $("deleteConfirm"), "Đang xóa…", "deleteError", async () => {
            const res = await BP.api(`/api/products/${encodeURIComponent(id)}`, { method: "DELETE" });
            deleting = null;
            if (detail?.id === id) closeModal("detailModal", true);
            return res.message || "Đã xóa sản phẩm.";
        });
    }

    // ---------------------------------------------------------------- sự kiện
    document.querySelectorAll("[data-icon]").forEach((el) => { el.outerHTML = BP.icon(el.dataset.icon); });
    $("addBtn").hidden = !BP.isAdmin();
    $("priceFilter").insertAdjacentHTML("beforeend", BP.PRICE_BANDS.map((b) => `<option value="${b.key}">${esc(b.label)}</option>`).join(""));
    $("discountFilter").insertAdjacentHTML("beforeend", Object.entries(BP.DISCOUNT_BANDS).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join(""));

    $("searchInput").addEventListener("input", BP.debounce(() => applyFilters(), 250));
    [...FILTERS, "sortSelect"].forEach((id) => $(id).addEventListener("change", () => applyFilters()));
    $("resetBtn").addEventListener("click", () => {
        ["searchInput", ...FILTERS].forEach((id) => { $(id).value = ""; });
        $("sortSelect").value = "name";
        applyFilters();
    });
    $("exportBtn").addEventListener("click", exportCsv);
    $("addBtn").addEventListener("click", () => openForm(null));
    $("tableBody").addEventListener("click", (event) => {
        const button = event.target.closest("[data-action]");
        const row = button && rowById.get(button.dataset.id);
        if (row) ({ view: openDetail, edit: openForm, delete: askDelete })[button.dataset.action](row);
    });

    ["reviewStar", "reviewSort"].forEach((id) => $(id).addEventListener("change", () => { detail.shown = REVIEW_PAGE; renderReviewList(); }));
    $("reviewMore").addEventListener("click", () => { detail.shown += REVIEW_PAGE * 2; renderReviewList(); });
    ["fPrice", "fListed"].forEach((id) => $(id).addEventListener("input", updateDiscount));
    $("stateBox").addEventListener("click", (e) => { if (e.target.closest("[data-retry]")) load(); });
    $("productForm").addEventListener("submit", saveForm);
    $("deleteConfirm").addEventListener("click", confirmDelete);

    // Đóng modal: nút [data-close], Esc, hoặc bấm nền (chỉ khi nhấn VÀ thả chuột đều trên nền).
    document.querySelectorAll(".modal-overlay").forEach((overlay) => {
        let downOnOverlay = false;
        overlay.addEventListener("mousedown", (e) => { downOnOverlay = e.target === overlay; });
        overlay.addEventListener("click", (e) => {
            if (e.target.closest("[data-close]")) closeModal(overlay.id);
            else if (downOnOverlay && e.target === overlay) closeModal(overlay.id);
            downOnOverlay = false;
        });
    });
    document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        const open = [...document.querySelectorAll(".modal-overlay:not([hidden])")].pop();
        if (open) closeModal(open.id);
    });

    BP.onProductsUpdated(load);
    load();
})();
