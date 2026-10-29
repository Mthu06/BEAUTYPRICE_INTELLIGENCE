/* script.js - trang Tổng quan (dashboard.html).
 * Mọi KPI / biểu đồ / nhận định tính từ danh sách sản phẩm ĐÃ LỌC.
 * Riêng biểu đồ xu hướng lấy từ /api/price-trend (toàn bộ lịch sử giá) và chỉ lọc theo nhà bán lẻ.
 */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const { COLORS } = BP;
    const NO_CATEGORY = "Không rõ";
    const EMPTY = "Không có sản phẩm phù hợp với bộ lọc.";
    const FILTER_IDS = ["retailerFilter", "categoryFilter", "brandFilter", "priceFilter"];
    const CHART_IDS = ["retailerChart", "priceChart", "categoryChart", "discountChart"];
    const DISCOUNT_KEYS = Object.keys(BP.DISCOUNT_BANDS);
    // Nhóm giảm giá có thứ tự -> thang tuần tự một màu (xám trung tính cho "Không giảm", xanh nhạt -> đậm)
    const DISCOUNT_COLORS = ["#dfe3ec", "#b9d4f5", "#7fb0ec", "#2a78d6", "#184f95"];

    let products = [], trend = [], trendError = "", brandLabels = new Map(), loadSeq = 0;

    // ---------------------------------------------------------------- tiện ích dữ liệu
    const priceOf = (p) => { const v = BP.toNumber(p.current_price_vnd); return v > 0 ? v : null; };
    const categoryOf = (p) => p.category || NO_CATEGORY;
    const rawBrand = (p) => String(p.brand || "").trim().replace(/\s+/g, " ");
    const brandKey = (p) => BP.normalizeText(rawBrand(p)).replace(/[^a-z0-9]/g, ""); // gộp "EUCERIN"/"Eucerin"
    const brandName = (p) => brandLabels.get(brandKey(p)) || rawBrand(p);
    const retailerName = (p) => p.source || p.retailer_id;
    const isDiscounted = (p) => (BP.toNumber(p.discount_percent) ?? 0) > 0;
    const pct = (n, total) => (total ? (n / total) * 100 : null);
    const bold = (text) => `<b>${BP.escapeHtml(text)}</b>`;
    const byLabel = (a, b) => a.label.localeCompare(b.label, "vi");
    const bySize = (a, b) => b.items.length - a.items.length || byLabel(a, b);
    const shortDay = (day) => `${day.slice(8, 10)}/${day.slice(5, 7)}`;

    /** Gom nhóm: [{key, label, items}] (bỏ khóa rỗng). */
    function groupBy(list, keyFn, labelFn = keyFn) {
        const map = new Map();
        for (const item of list) {
            const key = keyFn(item);
            if (!key) continue;
            if (!map.has(key)) map.set(key, { key, label: labelFn(item), items: [] });
            map.get(key).items.push(item);
        }
        return [...map.values()];
    }

    /** Tên hiển thị thương hiệu: cách viết phổ biến nhất, ưu tiên cách không viết hoa toàn bộ. */
    function buildBrandLabels() {
        brandLabels = new Map(groupBy(products, brandKey).map((g) => {
            const names = g.items.map(rawBrand);
            const mixed = names.filter((n) => n !== n.toUpperCase());
            return [g.key, BP.mostCommon(mixed.length ? mixed : names)[0]];
        }));
    }

    // ---------------------------------------------------------------- biểu đồ: phần dùng chung
    const font = (spec) => `${spec} ${window.Chart.defaults.font.family}`;
    const plainAxis = { grid: { display: false }, border: { color: COLORS.axis } };
    const countAxis = { beginAtZero: true, ticks: { precision: 0, callback: (v) => BP.formatNumber(v) }, grid: { color: COLORS.grid }, border: { display: false } };

    /** Nhãn số ở đầu mỗi cột (chuỗi đầu tiên). */
    const valueLabels = (format) => ({
        id: "valueLabels",
        afterDatasetsDraw(chart) {
            const { ctx } = chart, horizontal = chart.options.indexAxis === "y";
            ctx.save();
            Object.assign(ctx, { font: font("600 11px"), fillStyle: COLORS.ink2, textAlign: horizontal ? "left" : "center", textBaseline: horizontal ? "middle" : "bottom" });
            chart.getDatasetMeta(0).data.forEach((bar, i) => {
                const value = chart.data.datasets[0].data[i];
                if (value != null) ctx.fillText(format(value), horizontal ? bar.x + 6 : bar.x, horizontal ? bar.y : bar.y - 4);
            });
            ctx.restore();
        }
    });

    /** Tổng số ở giữa biểu đồ tròn. */
    const centerText = (value, label) => ({
        id: "centerText",
        afterDraw({ ctx, chartArea: a }) {
            const x = (a.left + a.right) / 2, y = (a.top + a.bottom) / 2;
            ctx.save();
            Object.assign(ctx, { textAlign: "center", fillStyle: COLORS.ink, font: font("750 22px"), textBaseline: "bottom" }).fillText(value, x, y + 3);
            Object.assign(ctx, { fillStyle: COLORS.muted, font: font("12px"), textBaseline: "top" }).fillText(label, x, y + 5);
            ctx.restore();
        }
    });

    /** Biểu đồ cột một chuỗi (dọc hoặc ngang) có nhãn số. */
    function barChart(id, labels, values, { horizontal = false, format, tooltip, valueAxis = countAxis }) {
        BP.chart(id, {
            type: "bar",
            data: { labels, datasets: [{ data: values, backgroundColor: COLORS.series[0] }] },
            options: {
                indexAxis: horizontal ? "y" : "x",
                layout: { padding: horizontal ? { right: 52 } : { top: 20 } },
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: tooltip } } },
                scales: horizontal ? { x: valueAxis, y: plainAxis } : { x: plainAxis, y: valueAxis }
            },
            plugins: [valueLabels(format)]
        });
    }

    /** Ẩn canvas và hiện ô trạng thái khi có message; trả về true nếu được phép vẽ. */
    function chartState(id, message, type = "empty") {
        const canvas = $(id);
        const slot = canvas.nextElementSibling || canvas.parentElement.appendChild(document.createElement("div"));
        canvas.hidden = Boolean(message);
        slot.innerHTML = message ? BP.stateHtml(message, type) : "";
        return !message;
    }

    // ---------------------------------------------------------------- bộ lọc
    function fillSelect(id, options, allLabel) {
        const select = $(id), current = select.value;
        select.innerHTML = `<option value="">${allLabel}</option>` +
            options.map(([value, label]) => `<option value="${BP.escapeHtml(value)}">${BP.escapeHtml(label)}</option>`).join("");
        select.value = options.some(([value]) => value === current) ? current : "";
    }

    function fillFilters() {
        const asOptions = (groups) => groups.map((g) => [g.key, `${g.label} (${BP.formatNumber(g.items.length)})`]);
        const noneLast = (a, b) => (a.key === NO_CATEGORY) - (b.key === NO_CATEGORY) || byLabel(a, b);
        fillSelect("retailerFilter", asOptions(groupBy(products, (p) => p.retailer_id, retailerName).sort(byLabel)), "Tất cả nhà bán lẻ");
        fillSelect("categoryFilter", asOptions(groupBy(products, categoryOf).sort(noneLast)), "Tất cả danh mục");
        fillSelect("brandFilter", asOptions(groupBy(products, brandKey, brandName).sort(byLabel)), "Tất cả thương hiệu");
    }

    function filtered() {
        const [retailer, category, brand, band] = FILTER_IDS.map((id) => $(id).value);
        return products.filter((p) => (!retailer || p.retailer_id === retailer) && (!category || categoryOf(p) === category)
            && (!brand || brandKey(p) === brand) && (!band || BP.priceBand(p.current_price_vnd) === band));
    }

    // ---------------------------------------------------------------- vẽ trang
    function render() {
        const list = filtered();
        const prices = list.map(priceOf).filter((v) => v !== null);
        const data = {
            list, prices,
            byRetailer: groupBy(list, (p) => p.retailer_id, retailerName).sort(bySize),
            byBrand: groupBy(list, brandKey, brandName).sort(bySize),
            byCategory: groupBy(list, categoryOf).map((g) => ({ ...g, median: BP.median(g.items.map(priceOf)) }))
                .filter((g) => g.median !== null).sort((a, b) => b.median - a.median),
            bands: BP.PRICE_BANDS.map((b) => ({ ...b, count: prices.filter((v) => BP.priceBand(v) === b.key).length }))
        };
        const active = FILTER_IDS.some((id) => $(id).value);
        $("resetFilters").disabled = !active;
        $("filterSummary").textContent = active ? `Đang xem ${BP.formatNumber(list.length)} / ${BP.formatNumber(products.length)} SP` : "Toàn bộ dữ liệu";
        [renderKpis, renderRetailerChart, renderBars, renderDiscountChart, renderBrands, renderInsights].forEach((fn) => fn(data));
        renderTrend();
    }

    function renderKpis({ list, prices, byRetailer, byBrand }) {
        const discounted = list.filter(isDiscounted);
        const set = (id, value, sub) => {
            Object.assign($(id), { textContent: value }).classList.remove("skeleton");
            $(id + "Sub").textContent = sub;
        };
        set("kpiTotal", BP.formatNumber(list.length), list.length === products.length ? `Từ ${byRetailer.length} nhà bán lẻ`
            : `${BP.formatPercent(pct(list.length, products.length))} của ${BP.formatNumber(products.length)} sản phẩm`);
        set("kpiBrands", BP.formatNumber(byBrand.length), byBrand[0] ? `Nhiều SP nhất: ${byBrand[0].label}` : "—");
        set("kpiMedian", BP.formatVnd(BP.median(prices)), prices.length ? `Trung bình ${BP.formatVnd(BP.average(prices))}` : "Chưa có giá hợp lệ");
        set("kpiDiscount", BP.formatNumber(discounted.length), discounted.length
            ? `${BP.formatPercent(pct(discounted.length, list.length))} sản phẩm · giảm trung vị ${BP.formatPercent(BP.median(discounted.map((p) => p.discount_percent)), 0)}`
            : "Không có sản phẩm giảm giá");
    }

    function renderRetailerChart({ list, byRetailer }) {
        if (!chartState("retailerChart", list.length ? "" : EMPTY)) return;
        const counts = byRetailer.map((g) => g.items.length);
        const describe = (n) => `${BP.formatNumber(n)} · ${BP.formatPercent(pct(n, list.length))}`;
        const baseLabels = window.Chart.overrides.doughnut.plugins.legend.labels.generateLabels;
        BP.chart("retailerChart", {
            type: "doughnut",
            data: {
                labels: byRetailer.map((g) => g.label),
                datasets: [{ data: counts, backgroundColor: byRetailer.map((g) => BP.retailerColor(g.key)), borderColor: "#fff", borderWidth: 2, hoverOffset: 6 }]
            },
            options: {
                cutout: "64%",
                layout: { padding: 6 },
                plugins: {
                    legend: {
                        position: matchMedia("(max-width: 600px)").matches ? "bottom" : "right",
                        labels: { padding: 16, generateLabels: (chart) => baseLabels(chart).map((item) => ({ ...item, text: `${item.text}   ${describe(counts[item.index])}` })) }
                    },
                    tooltip: { callbacks: { label: (c) => ` ${c.label}: ${describe(c.raw)}` } }
                }
            },
            plugins: [centerText(BP.formatNumber(list.length), "sản phẩm")]
        });
    }

    function renderBars({ prices, bands, byCategory }) {
        if (chartState("priceChart", prices.length ? "" : EMPTY)) {
            barChart("priceChart", bands.map((b) => b.label), bands.map((b) => b.count), {
                format: (v) => BP.formatNumber(v),
                tooltip: (c) => ` ${BP.formatNumber(c.raw)} sản phẩm (${BP.formatPercent(pct(c.raw, prices.length))})`
            });
        }
        if (chartState("categoryChart", byCategory.length ? "" : EMPTY)) {
            barChart("categoryChart", byCategory.map((g) => g.label), byCategory.map((g) => g.median), {
                horizontal: true, format: BP.formatVndShort, valueAxis: BP.vndAxis({ beginAtZero: true }),
                tooltip: (c) => ` Giá trung vị ${BP.formatVnd(c.raw)} · ${BP.formatNumber(byCategory[c.dataIndex].items.length)} sản phẩm`
            });
        }
    }

    /** Cột chồng 100%: tỷ lệ sản phẩm theo nhóm giảm giá trong từng nhà bán lẻ. */
    function renderDiscountChart({ list, byRetailer }) {
        if (!chartState("discountChart", list.length ? "" : EMPTY)) return;
        const counts = byRetailer.map((g) => DISCOUNT_KEYS.map((k) => g.items.filter((p) => BP.discountBucket(p.discount_percent) === k).length));
        BP.chart("discountChart", {
            type: "bar",
            data: {
                labels: byRetailer.map((g) => g.label),
                datasets: DISCOUNT_KEYS.map((k, i) => ({
                    label: BP.DISCOUNT_BANDS[k], data: byRetailer.map((g, r) => pct(counts[r][i], g.items.length)),
                    backgroundColor: DISCOUNT_COLORS[i], borderColor: "#fff", borderWidth: { left: 1, right: 1 }, borderRadius: 0, borderSkipped: false
                }))
            },
            options: {
                indexAxis: "y",
                plugins: {
                    legend: { position: "top", align: "start" },
                    tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${BP.formatNumber(counts[c.dataIndex][c.datasetIndex])} SP (${BP.formatPercent(c.raw)})` } }
                },
                scales: {
                    x: { stacked: true, min: 0, max: 100, ticks: { callback: (v) => v + "%" }, grid: { color: COLORS.grid }, border: { display: false } },
                    y: { stacked: true, ...plainAxis }
                }
            }
        });
    }

    function renderBrands({ list, byBrand }) {
        const top = byBrand.slice(0, 8);
        const topCount = top.reduce((sum, g) => sum + g.items.length, 0);
        $("brandList").innerHTML = top.length ? top.map((g) => `
            <div class="bar-item">
                <span class="bar-label" title="${BP.escapeHtml(g.label)}">${BP.escapeHtml(g.label)}</span>
                <div class="bar-track"><div class="bar-fill" style="width:${(g.items.length / top[0].items.length) * 100}%"></div></div>
                <span class="bar-value">${BP.formatNumber(g.items.length)} <span class="muted small">· ${BP.formatPercent(pct(g.items.length, list.length))}</span></span>
            </div>`).join("") : BP.stateHtml(EMPTY);
        $("brandNote").textContent = top.length ? `${BP.formatNumber(byBrand.length)} thương hiệu; top ${top.length} chiếm ${BP.formatPercent(pct(topCount, list.length))} ` +
            "số sản phẩm đang xem. Tên thương hiệu đã gộp khác biệt chữ hoa/thường." : "";
    }

    function renderTrend() {
        const retailer = $("retailerFilter").value;
        const rows = trend.filter((r) => !retailer || BP.retailerKey(r.retailer) === retailer);
        const days = [...new Set(rows.map((r) => r.day))].sort();
        const names = [...new Set(rows.map((r) => r.retailer))].sort((a, b) => a.localeCompare(b, "vi"));
        const lookup = new Map(rows.map((r) => [`${r.day}|${r.retailer}`, r]));
        const single = names.filter((n) => rows.filter((r) => r.retailer === n).length === 1);
        $("trendNote").textContent = days.length ? `${days.length} ngày thu thập (${shortDay(days[0])} – ${shortDay(days.at(-1))}).` +
            (single.length ? ` ${single.join(", ")} mới có 1 ngày dữ liệu nên hiển thị dạng điểm.` : "") : "";
        if (!chartState("trendChart", trendError || (rows.length ? "" : "Chưa có lịch sử giá cho lựa chọn này."), trendError ? "error" : "empty")) return;
        BP.chart("trendChart", {
            type: "line",
            data: {
                labels: days.map(shortDay),
                datasets: names.map((name) => ({
                    label: name, borderColor: BP.retailerColor(name), backgroundColor: BP.retailerColor(name),
                    data: days.map((d) => lookup.get(`${d}|${name}`)?.median_price ?? null),
                    pointRadius: 5, pointHoverRadius: 7, pointBorderColor: "#fff", pointBorderWidth: 2, spanGaps: true
                }))
            },
            options: {
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: { position: "bottom" },
                    tooltip: {
                        filter: (item) => item.raw != null,
                        callbacks: { label: (c) => ` ${c.dataset.label}: ${BP.formatVnd(c.raw)} (${BP.formatNumber(lookup.get(`${days[c.dataIndex]}|${c.dataset.label}`)?.snapshots)} bản ghi giá)` }
                    }
                },
                scales: { x: { ...plainAxis, offset: true }, y: BP.vndAxis({ grace: "8%" }) }
            }
        });
    }

    function renderInsights({ list, prices, byRetailer, byCategory, bands }) {
        const items = [];
        if (!list.length) items.push("Không có sản phẩm nào khớp bộ lọc hiện tại. Hãy nới bớt điều kiện hoặc bấm <b>Đặt lại bộ lọc</b>.");
        if (prices.length) {
            const top = bands.reduce((a, b) => (b.count > a.count ? b : a));
            items.push(`Khoảng giá phổ biến nhất là ${bold(top.label.replace(/^(Dưới|Từ)/, (w) => w.toLowerCase()))} với ${BP.formatNumber(top.count)} sản phẩm ` +
                `(${BP.formatPercent(pct(top.count, prices.length))}); một nửa số sản phẩm có giá dưới ${bold(BP.formatVnd(BP.median(prices)))}.`);
        }
        const ranked = byRetailer.map((g) => ({ label: g.label, median: BP.median(g.items.map(priceOf)) }))
            .filter((g) => g.median !== null).sort((a, b) => b.median - a.median);
        const [hi, lo] = [ranked[0], ranked.at(-1)];
        if (ranked.length >= 2) {
            items.push(`${bold(hi.label)} có giá trung vị cao nhất (${BP.formatVnd(hi.median)}), cao hơn ${BP.formatPercent(pct(hi.median - lo.median, lo.median), 0)} ` +
                `so với ${bold(lo.label)} – nơi có giá trung vị thấp nhất (${BP.formatVnd(lo.median)}).`);
        } else if (hi) {
            items.push(`Toàn bộ sản phẩm đang xem thuộc ${bold(hi.label)}, giá trung vị ${BP.formatVnd(hi.median)}.`);
        }
        const discounted = list.filter(isDiscounted);
        if (discounted.length) {
            const rates = byRetailer.map((g) => ({ label: g.label, rate: pct(g.items.filter(isDiscounted).length, g.items.length) })).sort((a, b) => b.rate - a.rate);
            items.push(`${bold(BP.formatPercent(pct(discounted.length, list.length)))} sản phẩm đang được giảm giá, mức giảm trung vị ` +
                BP.formatPercent(BP.median(discounted.map((p) => p.discount_percent)), 0) +
                (rates.length >= 2 ? `; ${bold(rates[0].label)} khuyến mãi nhiều nhất (${BP.formatPercent(rates[0].rate)} sản phẩm có giảm giá).` : "."));
        } else if (list.length) {
            items.push("Không có sản phẩm nào đang giảm giá trong nhóm đang xem.");
        }
        const cats = byCategory.filter((g) => g.key !== NO_CATEGORY);
        const rated = list.filter((p) => BP.toNumber(p.rating) > 0);
        if (cats.length >= 2) {
            items.push(`Danh mục đắt nhất theo giá trung vị là ${bold(cats[0].label)} (${BP.formatVnd(cats[0].median)}), ` +
                `rẻ nhất là ${bold(cats.at(-1).label)} (${BP.formatVnd(cats.at(-1).median)}).`);
        } else if (rated.length) {
            items.push(`${BP.formatNumber(rated.length)} sản phẩm có điểm đánh giá trên website, trung bình ${bold(BP.formatRating(BP.average(rated.map((p) => p.rating))) + "/5")}.`);
        }
        $("insightList").innerHTML = items.map((html, i) => `<li><span class="ins-no">${i + 1}</span><span>${html}</span></li>`).join("");
    }

    // ---------------------------------------------------------------- tải dữ liệu
    function showError(message) {
        $("loadError").innerHTML = BP.icon("alert") + `<div><b>Không tải được dữ liệu sản phẩm.</b> ${BP.escapeHtml(message)}</div>`;
        $("loadError").hidden = false;
        document.querySelectorAll(".kpi-value").forEach((el) => { el.textContent = "—"; el.classList.remove("skeleton"); });
        document.querySelectorAll(".kpi-sub").forEach((el) => { el.textContent = "Không có dữ liệu"; });
        CHART_IDS.forEach((id) => chartState(id, message, "error"));
        $("brandList").innerHTML = BP.stateHtml(message, "error");
        $("brandNote").textContent = $("insightList").innerHTML = "";
        renderTrend();
    }

    async function load() {
        const seq = ++loadSeq; // bỏ kết quả cũ nếu đã có lần tải mới hơn
        $("reloadBtn").disabled = true;
        const [prod, tr] = await Promise.allSettled([BP.api("/api/products"), BP.api("/api/price-trend")]);
        if (seq !== loadSeq) return;
        $("reloadBtn").disabled = false;
        trend = tr.status === "fulfilled" ? tr.value.trend || [] : [];
        trendError = tr.status === "rejected" ? `Không tải được xu hướng giá: ${tr.reason.message}` : "";
        if (prod.status === "rejected") return showError(prod.reason.message);
        $("loadError").hidden = true;
        products = prod.value.products || [];
        buildBrandLabels();
        fillFilters();
        render();
    }

    document.addEventListener("DOMContentLoaded", () => {
        document.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = BP.icon(el.dataset.icon); });
        $("reloadBtn").insertAdjacentHTML("afterbegin", BP.icon("refresh"));
        fillSelect("priceFilter", BP.PRICE_BANDS.map((b) => [b.key, b.label]), "Tất cả mức giá");
        [...CHART_IDS, "trendChart"].forEach((id) => chartState(id, "Đang tải dữ liệu...", "loading"));
        $("brandList").innerHTML = BP.stateHtml("Đang tải dữ liệu...", "loading");

        FILTER_IDS.forEach((id) => $(id).addEventListener("change", render));
        $("resetFilters").addEventListener("click", () => { FILTER_IDS.forEach((id) => { $(id).value = ""; }); render(); });
        $("reloadBtn").addEventListener("click", load);
        matchMedia("(max-width: 600px)").addEventListener("change", () => { if (products.length) render(); }); // đổi vị trí legend
        BP.onProductsUpdated(load); // tab Tra cứu thêm/sửa/xóa -> tải lại
        load();
    });
})();
