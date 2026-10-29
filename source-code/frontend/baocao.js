/* baocao.js - trang "Báo cáo thống kê": thống kê mô tả, danh sách min – max, chất lượng dữ liệu; in PDF và xuất CSV. */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const esc = BP.escapeHtml;
    const C = BP.COLORS;
    const NO_CATEGORY = "Chưa phân loại";
    const SOURCE_NAMES = { hasaki: "Hasaki", guardian: "Guardian" };
    const DISCOUNT_COLORS = ["#c3c7d3", "#b7d3f6", "#86b6ef", "#2a78d6", "#184f95"]; // thang tuần tự, "không giảm" màu xám
    const TABLE_LABELS = {
        retailers: "Nhà bán lẻ", categories: "Danh mục", products: "Sản phẩm", product_categories: "Sản phẩm – danh mục",
        price_snapshots: "Snapshot giá", reviews: "Review", collection_logs: "Nhật ký thu thập", product_matching: "Đối chiếu sản phẩm"
    };
    const METRICS = [
        { label: "Giá hiện tại (VND)", key: "current_price_vnd", fmt: (v) => BP.formatVnd(v), ok: (v) => v > 0 },
        { label: "Giá niêm yết (VND)", key: "listed_price_vnd", fmt: (v) => BP.formatVnd(v), ok: (v) => v > 0 },
        { label: "% giảm giá", key: "discount_percent", fmt: (v) => BP.formatPercent(v) },
        { label: "Rating sản phẩm", key: "rating", fmt: (v) => BP.formatNumber(v, "—", 2), ok: (v) => v > 0 },
        { label: "Số lượt đánh giá", key: "review_count", fmt: (v) => BP.formatNumber(v) }
    ];

    const now = new Date();
    const report = {};   // số liệu đã tính: dùng cho nhận định và xuất CSV
    const facts = {};    // vài con số cho phần nhận định

    // ---------------------------------------------------------------- tiện ích

    const num = BP.toNumber;
    const pct = (part, total, digits = 1) => BP.formatPercent(total ? (part / total) * 100 : null, digits);
    const values = (list, key, ok = () => true) => list.map((x) => num(x[key])).filter((v) => v !== null && ok(v));
    const max = (arr) => (arr.length ? Math.max(...arr) : null);
    const rt = (id, name) => `<span class="rt rt-${String(id).replace(/[^a-z_]/g, "")}">${esc(name)}</span>`;
    const tableHtml = (head, body) => `<table class="table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
    const fail = (ids, message) => ids.forEach((id) => {
        const el = $(id);
        if (!el) return;
        if (el.tagName === "CANVAS") { el.parentElement.classList.remove("is-loading"); el.parentElement.innerHTML = BP.stateHtml(message, "error"); }
        else el.innerHTML = BP.stateHtml(message, "error");
    });

    function groupBy(list, keyFn) {
        const map = new Map();
        for (const item of list) {
            const key = keyFn(item);
            if (!map.has(key)) map.set(key, []);
            map.get(key).push(item);
        }
        return map;
    }

    function describe(list) {
        const v = [...list].sort((a, b) => a - b);
        return v.length ? { n: v.length, min: v[0], max: v[v.length - 1], median: BP.median(v), mean: BP.average(v) } : { n: 0 };
    }

    /** Ghi giá trị ở đầu cột (chữ màu chữ). */
    const valueLabels = (format) => ({
        id: "valueLabels",
        afterDatasetsDraw(chart) {
            const { ctx } = chart;
            ctx.save();
            ctx.font = `600 11px ${Chart.defaults.font.family}`;
            ctx.fillStyle = C.ink2;
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            chart.getDatasetMeta(0).data.forEach((bar, i) => ctx.fillText(format(chart.data.datasets[0].data[i]), bar.x, bar.y - 4));
            ctx.restore();
        }
    });
    const drawn = (id) => $(id)?.parentElement.classList.remove("is-loading");

    // ---------------------------------------------------------------- 1. tổng quan + 2. min – max (từ /api/products)

    function minMaxRow(label, list) {
        const priced = list.filter((p) => num(p.current_price_vnd) > 0).sort((a, b) => a.current_price_vnd - b.current_price_vnd);
        const prices = priced.map((p) => p.current_price_vnd);
        return {
            label, n: list.length, cheapest: priced[0], dearest: priced[priced.length - 1],
            median: BP.median(prices), mean: BP.average(prices), maxDiscount: max(values(list, "discount_percent")),
            discounted: list.filter((p) => num(p.discount_percent) > 0).length
        };
    }

    function renderMinMax(id, rows, total, labelHtml) {
        const cell = (p) => p ? `<div class="mm"><b>${BP.formatVnd(p.current_price_vnd)}</b><small title="${esc(p.product_name)}">${esc(p.product_name)}</small></div>` : "—";
        const tr = (r, cls = "", label = labelHtml(r)) => `<tr class="${cls}"><td class="nowrap">${label}</td><td class="num">${BP.formatNumber(r.n)}</td>
            <td>${cell(r.cheapest)}</td><td>${cell(r.dearest)}</td><td class="num">${BP.formatVnd(r.median)}</td>
            <td class="num">${BP.formatVnd(r.mean)}</td><td class="num">${BP.formatPercent(r.maxDiscount)}</td></tr>`;
        $(id).innerHTML = tableHtml(
            `<th>Nhóm</th><th class="num">Số SP</th><th>Giá thấp nhất</th><th>Giá cao nhất</th><th class="num">Trung vị</th><th class="num">Trung bình</th><th class="num">Giảm tối đa</th>`,
            rows.map((r) => tr(r)).join("") + tr(total, "total-row", "Tất cả"));
    }

    const minMaxCsv = (rows, total) => [["Nhóm", "Số SP", "Giá min (VND)", "SP rẻ nhất", "Giá max (VND)", "SP đắt nhất", "Giá trung vị", "Giá trung bình", "% giảm tối đa"],
        ...[...rows, { ...total, label: "Tất cả" }].map((r) => [r.label, r.n, r.cheapest?.current_price_vnd ?? "", r.cheapest?.product_name ?? "",
            r.dearest?.current_price_vnd ?? "", r.dearest?.product_name ?? "", Math.round(r.median ?? 0) || "", Math.round(r.mean ?? 0) || "", r.maxDiscount ?? ""])];

    function renderProducts(products) {
        const prices = values(products, "current_price_vnd", (v) => v > 0);
        const price = describe(prices);
        const discounted = products.filter((p) => num(p.discount_percent) > 0);
        const brands = groupBy(products.filter((p) => p.brand), (p) => p.brand.trim().toLowerCase());
        const retailers = groupBy(products, (p) => p.retailer_id);
        const categories = groupBy(products, (p) => p.category || NO_CATEGORY);
        const topBrands = [...brands.values()].sort((a, b) => b.length - a.length);
        Object.assign(facts, { products, price, discounted, brandCount: brands.size, retailerCount: retailers.size });

        // KPI
        $("kpiProducts").textContent = BP.formatNumber(products.length);
        $("kpiProductsSub").textContent = `${retailers.size} nhà bán lẻ · ${[...categories.keys()].filter((c) => c !== NO_CATEGORY).length} danh mục`;
        $("kpiBrands").textContent = BP.formatNumber(brands.size);
        $("kpiBrandsSub").textContent = topBrands.length ? `Nhiều SP nhất: ${topBrands[0][0].brand} (${BP.formatNumber(topBrands[0].length)})` : "—";
        $("kpiMedian").textContent = BP.formatVnd(price.median);
        $("kpiMedianSub").textContent = price.n ? `Khoảng ${BP.formatVndShort(price.min)} – ${BP.formatVndShort(price.max)}` : "—";
        $("kpiMean").textContent = BP.formatVnd(price.mean);
        $("kpiMeanSub").textContent = price.n ? `Cao hơn trung vị ${pct(price.mean - price.median, price.median, 0)} (lệch phải)` : "—";
        $("kpiDiscount").textContent = pct(discounted.length, products.length);
        $("kpiDiscountSub").textContent = `${BP.formatNumber(discounted.length)} SP · giảm trung vị ${BP.formatPercent(BP.median(discounted.map((p) => p.discount_percent)))}`;
        report.overview = [["Chỉ số", "Giá trị"], ["Tổng sản phẩm", products.length], ["Số thương hiệu", brands.size], ["Số nhà bán lẻ", retailers.size],
            ["Giá trung vị (VND)", Math.round(price.median)], ["Giá trung bình (VND)", Math.round(price.mean)], ["Giá thấp nhất (VND)", price.min],
            ["Giá cao nhất (VND)", price.max], ["Số SP đang giảm giá", discounted.length], ["% SP đang giảm giá", ((discounted.length / products.length) * 100).toFixed(1)]];

        // min – max theo danh mục / nhà bán lẻ
        const total = minMaxRow("Tất cả", products);
        const byCategory = [...categories].map(([k, list]) => minMaxRow(k, list))
            .sort((a, b) => (a.label === NO_CATEGORY) - (b.label === NO_CATEGORY) || b.n - a.n);
        const byRetailer = [...retailers].map(([id, list]) => ({ ...minMaxRow(list[0].source || id, list), id })).sort((a, b) => b.n - a.n);
        renderMinMax("categoryTable", byCategory, total, (r) => r.label === NO_CATEGORY ? `<span class="muted">${esc(r.label)}</span>` : esc(r.label));
        renderMinMax("retailerTable", byRetailer, total, (r) => rt(r.id, r.label));
        report.byCategory = minMaxCsv(byCategory, total);
        report.byRetailer = minMaxCsv(byRetailer, total);
        Object.assign(facts, { byCategory, byRetailer, total });

        // min – max các chỉ số
        const metricRows = METRICS.map((m) => ({ ...m, d: describe(values(products, m.key, m.ok)) }));
        $("metricTable").innerHTML = tableHtml(
            `<th>Chỉ số</th><th class="num">Hợp lệ</th><th class="num">Thiếu</th><th class="num">Min</th><th class="num">Max</th><th class="num">Trung vị</th><th class="num">Trung bình</th>`,
            metricRows.map(({ label, fmt, d }) => `<tr><td class="nowrap"><b>${esc(label)}</b></td><td class="num">${BP.formatNumber(d.n)}</td>
                <td class="num">${BP.formatNumber(products.length - d.n)} <span class="muted small">(${pct(products.length - d.n, products.length, 0)})</span></td>
                <td class="num">${d.n ? fmt(d.min) : "—"}</td><td class="num">${d.n ? fmt(d.max) : "—"}</td>
                <td class="num">${d.n ? fmt(d.median) : "—"}</td><td class="num">${d.n ? fmt(d.mean) : "—"}</td></tr>`).join(""));
        report.metrics = [["Chỉ số", "Số giá trị hợp lệ", "Thiếu", "Min", "Max", "Trung vị", "Trung bình"],
            ...metricRows.map(({ label, d }) => [label, d.n, products.length - d.n, d.min ?? "", d.max ?? "", d.median ?? "", d.mean == null ? "" : d.mean.toFixed(2)])];
        facts.metricRows = metricRows;

        renderDistributions(products, discounted);
        renderBrands(topBrands.slice(0, 10), products.length);
    }

    // ---------------------------------------------------------------- 3. phân bố

    function renderDistributions(products, discounted) {
        const priced = products.filter((p) => num(p.current_price_vnd) > 0);
        const bandCounts = BP.PRICE_BANDS.map((b) => priced.filter((p) => BP.priceBand(p.current_price_vnd) === b.key).length);
        BP.chart("priceChart", {
            type: "bar",
            data: { labels: BP.PRICE_BANDS.map((b) => b.label), datasets: [{ label: "Số sản phẩm", data: bandCounts, backgroundColor: C.series[0] }] },
            options: {
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${BP.formatNumber(c.raw)} SP (${pct(c.raw, priced.length)})` } } },
                scales: { x: { grid: { display: false } }, y: { beginAtZero: true, grace: "10%", ticks: { callback: (v) => BP.formatNumber(v) }, grid: { color: C.grid }, border: { display: false } } }
            },
            plugins: [valueLabels((v) => `${BP.formatNumber(v)} · ${pct(v, priced.length, 0)}`)]
        });
        drawn("priceChart");

        const keys = Object.keys(BP.DISCOUNT_BANDS);
        const discountCounts = keys.map((k) => products.filter((p) => BP.discountBucket(p.discount_percent) === k).length);
        BP.chart("discountChart", {
            type: "doughnut",
            data: {
                labels: keys.map((k, i) => `${BP.DISCOUNT_BANDS[k]} · ${pct(discountCounts[i], products.length)}`),
                datasets: [{ data: discountCounts, backgroundColor: DISCOUNT_COLORS, borderColor: "#fff", borderWidth: 2 }]
            },
            options: {
                cutout: "58%",
                plugins: {
                    legend: { position: innerWidth < 600 ? "bottom" : "right" },
                    tooltip: { callbacks: { label: (c) => `${BP.DISCOUNT_BANDS[keys[c.dataIndex]]}: ${BP.formatNumber(c.raw)} SP (${pct(c.raw, products.length)})` } }
                }
            }
        });
        drawn("discountChart");

        report.distribution = [["Phân bố", "Nhóm", "Số SP", "Tỷ lệ (%)"],
            ...BP.PRICE_BANDS.map((b, i) => ["Khoảng giá", b.label, bandCounts[i], ((bandCounts[i] / priced.length) * 100).toFixed(1)]),
            ...keys.map((k, i) => ["Mức giảm giá", BP.DISCOUNT_BANDS[k], discountCounts[i], ((discountCounts[i] / products.length) * 100).toFixed(1)])];
        facts.bands = BP.PRICE_BANDS.map((b, i) => ({ label: b.label, n: bandCounts[i] }));
    }

    function renderBrands(top, total) {
        const rows = top.map((list) => ({
            brand: BP.mostCommon(list.map((p) => p.brand))?.[0] || list[0].brand, n: list.length,
            retailers: new Set(list.map((p) => p.retailer_id)).size,
            median: BP.median(list.map((p) => p.current_price_vnd)), mean: BP.average(values(list, "current_price_vnd", (v) => v > 0)),
            discount: BP.average(values(list, "discount_percent"))
        }));
        const widest = rows[0]?.n || 1;
        $("brandTable").innerHTML = tableHtml(
            `<th class="rank">#</th><th>Thương hiệu</th><th class="num">Số SP</th><th>Tỷ trọng</th><th class="num">Nhà bán lẻ</th><th class="num">Giá trung vị</th><th class="num">Giá TB</th><th class="num">Giảm TB</th>`,
            rows.map((r, i) => `<tr><td class="rank">${i + 1}</td><td><b>${esc(r.brand)}</b></td><td class="num">${BP.formatNumber(r.n)}</td>
                <td><div class="share"><div class="bar-track"><div class="bar-fill" style="width:${((r.n / widest) * 100).toFixed(1)}%"></div></div><span class="small">${pct(r.n, total)}</span></div></td>
                <td class="num">${r.retailers}</td><td class="num">${BP.formatVnd(r.median)}</td><td class="num">${BP.formatVnd(r.mean)}</td><td class="num">${BP.formatPercent(r.discount)}</td></tr>`).join(""));
        report.brands = [["#", "Thương hiệu", "Số SP", "Tỷ trọng (%)", "Số nhà bán lẻ", "Giá trung vị (VND)", "Giá TB (VND)", "Giảm TB (%)"],
            ...rows.map((r, i) => [i + 1, r.brand, r.n, ((r.n / total) * 100).toFixed(1), r.retailers, Math.round(r.median), Math.round(r.mean), r.discount == null ? "" : r.discount.toFixed(1)])];
        facts.topBrand = rows[0];
    }

    // ---------------------------------------------------------------- 4. đánh giá (từ /api/reviews)

    function renderReviews(reviews) {
        const total = reviews.length;
        const sources = [...groupBy(reviews, (r) => r.source || "khác")].sort((a, b) => b[1].length - a[1].length);
        const name = (s) => SOURCE_NAMES[s] || s;
        const share = (list, key) => { const known = list.filter((r) => r[key] !== null && r[key] !== undefined); return { known: known.length, yes: known.filter((r) => r[key]).length }; };
        const stars = (list) => [1, 2, 3, 4, 5].map((s) => list.filter((r) => num(r.rating) !== null && Math.min(5, Math.max(1, Math.floor(r.rating))) === s).length);
        const stats = sources.map(([s, list]) => ({ s, name: name(s), n: list.length, avg: BP.average(values(list, "rating")), stars: stars(list), bought: share(list, "is_bought"), images: share(list, "has_images") }));
        const bought = share(reviews, "is_bought"), images = share(reviews, "has_images");
        const linked = reviews.filter((r) => r.product_id).length;

        $("kpiReviews").textContent = BP.formatNumber(total);
        $("kpiReviewsSub").textContent = stats.map((x) => `${x.name} ${BP.formatNumber(x.n)}`).join(" · ") || "—";

        const tile = (label, value, sub) => `<div class="stat-tile"><div class="label">${esc(label)}</div><div class="value">${value}</div><div class="sub">${esc(sub)}</div></div>`;
        $("reviewTiles").innerHTML = [
            tile("Tổng số review", BP.formatNumber(total), `Nối được với sản phẩm: ${pct(linked, total)}`),
            ...stats.map((x) => tile(`Điểm TB ${x.name}`, `${BP.formatNumber(x.avg, "—", 2)} / 5`, `${BP.formatNumber(x.n)} review (${pct(x.n, total)})`)),
            tile("Đã mua hàng", pct(bought.yes, bought.known), `trên ${BP.formatNumber(bought.known)} review có thông tin`),
            tile("Có ảnh kèm theo", pct(images.yes, images.known), `trên ${BP.formatNumber(images.known)} review có thông tin`)
        ].join("");

        const lead = stats[0];
        const fiveStar = stats.reduce((s, x) => s + x.stars[4], 0);
        if (lead && total) {
            $("reviewNote").innerHTML = BP.icon("info") + `<div><b>${esc(lead.name)}</b> chiếm ~${pct(lead.n, total, 0)} số review nên các tỷ lệ chung chủ yếu phản ánh ${esc(lead.name)} — nên so sánh theo từng nguồn. `
                + `${pct(fiveStar, total, 0)} review là 5 sao: điểm đánh giá lệch mạnh về phía tích cực, ít phân biệt được chất lượng sản phẩm.</div>`;
            $("reviewNote").hidden = false;
        }

        BP.chart("starChart", {
            type: "bar",
            data: {
                labels: ["1 sao", "2 sao", "3 sao", "4 sao", "5 sao"],
                datasets: stats.map((x) => ({ label: x.name, data: x.stars.map((c) => (x.n ? (c / x.n) * 100 : 0)), counts: x.stars, backgroundColor: BP.retailerColor(x.s) }))
            },
            options: {
                plugins: {
                    legend: { position: "top", align: "end" },
                    tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${BP.formatPercent(c.raw)} (${BP.formatNumber(c.dataset.counts[c.dataIndex])} review)` } }
                },
                scales: {
                    x: { grid: { display: false } },
                    y: { beginAtZero: true, max: 100, ticks: { callback: (v) => v + "%" }, grid: { color: C.grid }, border: { display: false } }
                }
            }
        });
        drawn("starChart");

        $("starTable").innerHTML = tableHtml(
            `<th>Nguồn</th><th class="num">Số review</th>${[1, 2, 3, 4, 5].map((s) => `<th class="num">${s} ★</th>`).join("")}<th class="num">Điểm TB</th><th class="num">Đã mua</th><th class="num">Có ảnh</th>`,
            stats.map((x) => `<tr><td>${rt(x.s, x.name)}</td><td class="num">${BP.formatNumber(x.n)}</td>${x.stars.map((c) => `<td class="num">${pct(c, x.n)}</td>`).join("")}
                <td class="num"><b>${BP.formatNumber(x.avg, "—", 2)}</b></td><td class="num">${pct(x.bought.yes, x.bought.known)}</td><td class="num">${pct(x.images.yes, x.images.known)}</td></tr>`).join(""));

        report.reviews = [["Nguồn", "Số review", "Tỷ trọng (%)", "1 sao", "2 sao", "3 sao", "4 sao", "5 sao", "Điểm TB", "% đã mua", "% có ảnh"],
            ...stats.map((x) => [x.name, x.n, ((x.n / total) * 100).toFixed(1), ...x.stars, x.avg == null ? "" : x.avg.toFixed(2),
                x.bought.known ? ((x.bought.yes / x.bought.known) * 100).toFixed(1) : "", x.images.known ? ((x.images.yes / x.images.known) * 100).toFixed(1) : ""])];
        Object.assign(facts, { reviewTotal: total, reviewLead: lead, fiveStar });
    }

    // ---------------------------------------------------------------- 5. chất lượng dữ liệu (từ /api/data-quality)

    function renderQuality(dq) {
        const steps = dq.steps || [];
        $("etlRun").textContent = `Nhật ký ETL lần dựng CSDL gần nhất: ${BP.formatDate(dq.run_at, true)} · ${steps.length} bước xử lý`;
        $("stepTable").innerHTML = steps.length ? tableHtml(
            `<th class="rank">#</th><th>Bước xử lý</th><th>Bảng</th><th class="num">Vào</th><th class="num">Ra</th><th class="num">Tác động</th><th>Ghi chú</th>`,
            steps.map((s, i) => {
                const removed = s.rows_in - s.rows_out;
                return `<tr><td class="step-no">${i + 1}</td><td class="step-name"><b>${esc(s.step)}</b></td><td><code>${esc(s.table_name)}</code></td>
                    <td class="num">${BP.formatNumber(s.rows_in)}</td>
                    <td class="num">${BP.formatNumber(s.rows_out)}${removed > 0 ? ` <span class="badge badge-warn">−${BP.formatNumber(removed)}</span>` : ""}</td>
                    <td class="num">${s.rows_affected ? `<b>${BP.formatNumber(s.rows_affected)}</b> <span class="muted small">(${pct(s.rows_affected, s.rows_in, 0)})</span>` : '<span class="muted">0</span>'}</td>
                    <td class="note">${esc(s.note || "")}</td></tr>`;
            }).join("")) : BP.stateHtml("Chưa có nhật ký làm sạch (etl_log trống).");

        const order = Object.keys(TABLE_LABELS);
        const tables = Object.entries(dq.tables || {}).sort((a, b) => (order.indexOf(a[0]) + 1 || 99) - (order.indexOf(b[0]) + 1 || 99));
        $("tableTiles").innerHTML = tables.map(([t, n]) => `<div class="stat-tile"><div class="label">${esc(TABLE_LABELS[t] || t)}</div><div class="value">${BP.formatNumber(n)}</div><div class="sub"><code>${esc(t)}</code></div></div>`).join("");

        const coll = dq.collection || [];
        const runs = coll.reduce((s, c) => s + c.runs, 0), success = coll.reduce((s, c) => s + c.success, 0);
        const summary = `<div class="stat-tiles collect-summary"><div class="stat-tile"><div class="label">Lần thu thập</div><div class="value">${BP.formatNumber(runs)}</div></div>`
            + `<div class="stat-tile"><div class="label">Thành công</div><div class="value">${BP.formatNumber(success)}</div></div>`
            + `<div class="stat-tile"><div class="label">Tỷ lệ</div><div class="value">${pct(success, runs, 0)}</div></div></div>`;
        $("collectionList").innerHTML = coll.length ? summary + `<div class="collect">${coll.map((c) => `<div class="collect-row">
                ${rt(BP.retailerKey(c.retailer), c.retailer || "—")}
                <div class="bar-track"><div class="bar-fill" style="width:${c.runs ? ((c.success / c.runs) * 100).toFixed(1) : 0}%"></div></div>
                <span class="bar-value">${BP.formatNumber(c.success)}/${BP.formatNumber(c.runs)} · ${pct(c.success, c.runs, 0)}</span></div>`).join("")}</div>`
            : BP.stateHtml("Chưa có nhật ký thu thập.");

        report.quality = [["Bước", "Bảng", "Số dòng vào", "Số dòng ra", "Số dòng tác động", "Ghi chú"],
            ...steps.map((s) => [s.step, s.table_name, s.rows_in, s.rows_out, s.rows_affected, s.note || ""]),
            [], ["Bảng CSDL", "Số dòng"], ...tables.map(([t, n]) => [t, n]),
            [], ["Nhà bán lẻ", "Số lần thu thập", "Thành công", "Tỷ lệ (%)"], ...coll.map((c) => [c.retailer, c.runs, c.success, c.runs ? ((c.success / c.runs) * 100).toFixed(1) : ""])];
        facts.dq = { steps, coll };
    }

    // ---------------------------------------------------------------- nhận định

    function renderInsights() {
        const items = [];
        const f = facts;
        if (f.products) {
            const top = f.byRetailer[0];
            items.push(`Bộ dữ liệu gồm <b>${BP.formatNumber(f.products.length)}</b> sản phẩm của <b>${BP.formatNumber(f.brandCount)}</b> thương hiệu từ ${f.retailerCount} nhà bán lẻ; <b>${esc(top.label)}</b> đóng góp nhiều nhất (${pct(top.n, f.products.length)}).`);
            const band = f.bands.reduce((a, b) => (b.n > a.n ? b : a));
            items.push(`Giá trung vị <b>${BP.formatVnd(f.price.median)}</b> thấp hơn giá trung bình <b>${BP.formatVnd(f.price.mean)}</b>: phân phối giá lệch phải do một số sản phẩm cao cấp. Khoảng giá phổ biến nhất là <b>${esc(band.label)}</b> (${pct(band.n, f.price.n)}).`);
            const cats = f.byCategory.filter((c) => c.label !== NO_CATEGORY && c.median != null);
            if (cats.length) {
                const hi = cats.reduce((a, b) => (b.median > a.median ? b : a)), lo = cats.reduce((a, b) => (b.median < a.median ? b : a));
                items.push(`Danh mục đắt nhất theo giá trung vị là <b>${esc(hi.label)}</b> (${BP.formatVnd(hi.median)}), rẻ nhất là <b>${esc(lo.label)}</b> (${BP.formatVnd(lo.median)}). Sản phẩm đắt nhất toàn bộ: ${esc(f.total.dearest?.product_name || "—")} (<b>${BP.formatVnd(f.total.dearest?.current_price_vnd)}</b>).`);
            }
            const rts = f.byRetailer.map((r) => ({ ...r, rate: r.discounted / r.n }));
            const most = rts.reduce((a, b) => (b.rate > a.rate ? b : a)), least = rts.reduce((a, b) => (b.rate < a.rate ? b : a));
            items.push(`<b>${pct(f.discounted.length, f.products.length, 0)}</b> sản phẩm đang giảm giá; ${esc(most.label)} khuyến mãi nhiều nhất (${pct(most.discounted, most.n, 0)} SP), ${esc(least.label)} ít nhất (${pct(least.discounted, least.n, 0)}). Mức giảm sâu nhất ghi nhận: <b>${BP.formatPercent(f.total.maxDiscount)}</b>.`);
        }
        if (f.reviewLead) {
            items.push(`Review chủ yếu đến từ <b>${esc(f.reviewLead.name)}</b> (${pct(f.reviewLead.n, f.reviewTotal, 0)}) và <b>${pct(f.fiveStar, f.reviewTotal, 0)}</b> là 5 sao — rating hữu ích để lọc sản phẩm có vấn đề hơn là xếp hạng sản phẩm tốt.`);
        }
        if (f.dq && f.products) {
            const biggest = f.dq.steps.reduce((a, b) => (b.rows_affected > (a?.rows_affected ?? -1) ? b : a), null);
            const missingCat = f.byCategory.find((c) => c.label === NO_CATEGORY)?.n || 0;
            const rating = f.metricRows.find((m) => m.key === "rating").d.n;
            const runs = f.dq.coll.reduce((s, c) => s + c.runs, 0), ok = f.dq.coll.reduce((s, c) => s + c.success, 0);
            items.push(`Quy trình làm sạch gồm ${f.dq.steps.length} bước${biggest ? `, tác động nhiều nhất ở bước “${esc(biggest.step)}” (${BP.formatNumber(biggest.rows_affected)} dòng)` : ""}. `
                + `Còn ${pct(missingCat, f.products.length, 0)} SP chưa có danh mục chính và ${pct(f.products.length - rating, f.products.length, 0)} SP chưa có rating; crawler thành công ${ok}/${runs} lần (${pct(ok, runs, 0)}).`);
        }
        $("insights").innerHTML = items.length ? items.map((h, i) => `<li><span class="ins-no">${i + 1}</span><span>${h}</span></li>`).join("")
            : `<li>${BP.stateHtml("Không đủ dữ liệu để rút ra nhận định.")}</li>`;
        report.insights = [["Nhận định"], ...items.map((h) => [h.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#039;/g, "'")])];
    }

    // ---------------------------------------------------------------- xuất CSV (một file nhiều phần)

    function exportCsv() {
        const parts = [["TỔNG QUAN", report.overview], ["MIN – MAX THEO DANH MỤC", report.byCategory], ["MIN – MAX THEO NHÀ BÁN LẺ", report.byRetailer],
            ["MIN – MAX CÁC CHỈ SỐ", report.metrics], ["PHÂN BỐ", report.distribution], ["TOP 10 THƯƠNG HIỆU", report.brands],
            ["THỐNG KÊ REVIEW", report.reviews], ["CHẤT LƯỢNG DỮ LIỆU", report.quality], ["NHẬN ĐỊNH", report.insights]];
        const rows = [["BÁO CÁO THỐNG KÊ - BeautyPrice Intelligence"], [`Lập lúc: ${BP.formatDate(now.toISOString(), true)}`]];
        parts.filter(([, data]) => data).forEach(([title, data], i) => rows.push([], [`${i + 1}. ${title}`], ...data));
        BP.downloadCsv(`bao-cao-thong-ke-${now.toISOString().slice(0, 10)}.csv`, rows);
        BP.toast("Đã xuất báo cáo ra file CSV.");
    }

    // ---------------------------------------------------------------- khởi động

    async function init() {
        document.querySelectorAll("[data-icon]").forEach((el) => {
            if (el.tagName === "SPAN") el.outerHTML = BP.icon(el.dataset.icon); else el.innerHTML = BP.icon(el.dataset.icon);
        });
        $("reportTime").textContent = $("footTime").textContent = BP.formatDate(now.toISOString(), true);
        ["categoryTable", "retailerTable", "metricTable", "brandTable", "stepTable"].forEach((id) => { $(id).innerHTML = BP.stateHtml("Đang tải...", "loading"); });
        $("printBtn").addEventListener("click", () => window.print());
        $("exportBtn").addEventListener("click", exportCsv);

        const [products, reviews, quality] = await Promise.allSettled([BP.api("/api/products"), BP.api("/api/reviews"), BP.api("/api/data-quality")]);
        const guard = (result, render, ids) => {
            if (result.status === "fulfilled") {
                try { render(result.value); return; } catch (err) { console.error(err); fail(ids, `Lỗi xử lý số liệu: ${err.message}`); return; }
            }
            fail(ids, result.reason?.message || "Không tải được dữ liệu.");
        };
        guard(products, (d) => renderProducts(d.products || []), ["categoryTable", "retailerTable", "metricTable", "brandTable", "priceChart", "discountChart"]);
        guard(reviews, (d) => renderReviews(d.reviews || []), ["reviewTiles", "starChart", "starTable"]);
        guard(quality, renderQuality, ["stepTable", "tableTiles", "collectionList"]);
        if (products.status === "rejected") ["kpiProductsSub", "kpiBrandsSub", "kpiMedianSub", "kpiMeanSub", "kpiDiscountSub"].forEach((id) => { $(id).textContent = "Lỗi tải sản phẩm"; });
        if (reviews.status === "rejected") $("kpiReviewsSub").textContent = "Lỗi tải review";
        try { renderInsights(); } catch (err) { console.error(err); $("insights").innerHTML = `<li>${BP.stateHtml(err.message, "error")}</li>`; }
        $("exportBtn").disabled = !Object.keys(report).length;
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
