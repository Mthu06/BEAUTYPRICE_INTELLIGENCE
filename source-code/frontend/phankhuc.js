/* phankhuc.js - trang Phân khúc sản phẩm (K-Means). Dữ liệu: /api/clusters, /api/clusters/summary, /api/clusters/features. */
(function () {
    "use strict";

    const { COLORS, escapeHtml: esc } = BP;
    const $ = (id) => document.getElementById(id);
    const PAGE_SIZE = 50;
    const NONE = "none"; // giá trị bộ lọc "Chưa phân cụm"

    const state = { products: [], summary: [], page: 1 };

    const clusterName = (c) => (c === null || c === undefined ? "Chưa phân cụm" : `Cụm ${c}`);
    const clusterColor = (c) => COLORS.series[c] || COLORS.muted;
    const clusterDot = (c) => `<span class="dot ${c === null || c === undefined || c > 7 ? "cl-none" : "cl-" + c}"></span>`;
    const retailerName = (id) => BP.RETAILER_NAMES[BP.retailerKey(id)] || id || "—";
    const pct = (part, total) => (total ? (part / total) * 100 : null);

    /** Plugin vẽ nhãn trực tiếp (chữ màu mực, không dùng màu chuỗi). getLabels(chart) -> [{x, y, text, align, baseline}]. */
    const labelPlugin = (getLabels) => ({
        id: "directLabels",
        afterDatasetsDraw(chart) {
            const { ctx } = chart;
            ctx.save();
            ctx.font = `600 11px ${Chart.defaults.font.family}`;
            ctx.fillStyle = COLORS.ink2;
            for (const l of getLabels(chart)) {
                ctx.textAlign = l.align || "center";
                ctx.textBaseline = l.baseline || "bottom";
                ctx.fillText(l.text, l.x, l.y);
            }
            ctx.restore();
        }
    });

    /** Các phần tử đạt cực trị (giữ tất cả khi hòa). dir = 1: lớn nhất, -1: nhỏ nhất. */
    function extremes(list, key, dir = 1) {
        const valid = list.filter((s) => s[key] !== null && s[key] !== undefined);
        if (!valid.length) return [];
        const best = dir > 0 ? Math.max(...valid.map((s) => s[key])) : Math.min(...valid.map((s) => s[key]));
        return valid.filter((s) => Math.abs(s[key] - best) < 1e-9);
    }
    const nameList = (list) => list.map((s) => `<b>${clusterName(s.cluster)}</b>`).join(", ");
    const superlative = (list, word) => `${nameList(list)} ${list.length > 1 ? "cùng " : ""}${word}`;

    // ---------------------------------------------------------------- tải dữ liệu

    async function load() {
        document.querySelectorAll("[data-icon]").forEach((el) => el.insertAdjacentHTML("afterbegin", BP.icon(el.dataset.icon)));
        $("clusterCards").innerHTML = BP.stateHtml("Đang tải...", "loading");
        $("productBody").innerHTML = `<tr><td colspan="7">${BP.stateHtml("Đang tải...", "loading")}</td></tr>`;
        try {
            const [all, summary, features] = await Promise.all([
                BP.api("/api/clusters"), BP.api("/api/clusters/summary"), BP.api("/api/clusters/features")]);
            state.products = all.products || [];
            state.summary = enrich(summary.data || [], state.products);
            renderKpis(all, features);
            renderCharts(features);
            renderCards();
            renderFeatures(features);
            renderInsights(features);
            setupTable(all.unclustered > 0);
            $("trainedAt").textContent = `Huấn luyện: ${BP.formatDate(features.trained_at, true)}`;
        } catch (err) {
            $("pageError").innerHTML = `<div class="notice notice-bad">${BP.icon("alert")}<span>${esc(err.message)}</span></div>`;
            $("pageError").classList.add("mt");
            for (const id of ["clusterCards", "featureList", "insights"]) $(id).innerHTML = BP.stateHtml(err.message, "error");
            $("productBody").innerHTML = `<tr><td colspan="7">${BP.stateHtml(err.message, "error")}</td></tr>`;
        }
    }

    /** Thêm cơ cấu nhà bán lẻ / danh mục (đếm từ danh sách sản phẩm) vào bản tóm tắt từng cụm. */
    function enrich(summary, products) {
        return summary.map((s) => {
            const group = products.filter((p) => p.cluster === s.cluster);
            const count = (key) => group.reduce((m, p) => m.set(p[key], (m.get(p[key]) || 0) + 1), new Map());
            const retailers = count("retailer_id");
            const categories = count("primary_category");
            const topCat = BP.mostCommon(group.map((p) => p.primary_category || "Không rõ"));
            return {
                ...s, retailers,
                retailerShare: pct(retailers.get(s.top_retailer) || 0, group.length),
                categoryShare: topCat ? pct(topCat[1], group.length) : null,
                categoryCount: categories.size
            };
        });
    }

    // ---------------------------------------------------------------- KPI

    function renderKpis(all, features) {
        $("kpiTotal").textContent = BP.formatNumber(all.total_products);
        $("kpiK").textContent = BP.formatNumber(features.k ?? all.total_clusters);
        $("kpiKSub").textContent = `Silhouette ${BP.formatNumber(features.silhouette, "—", 3)}`;
        const largest = extremes(state.summary, "product_count");
        $("kpiLargest").textContent = largest.map((s) => clusterName(s.cluster)).join(", ") || "—";
        $("kpiLargestSub").textContent = largest.length
            ? `${BP.formatNumber(largest[0].product_count)} SP · ${BP.formatPercent(pct(largest[0].product_count, all.total_products))} tổng số`
            : "—";
        $("kpiUnclustered").textContent = BP.formatNumber(all.unclustered);
        $("kpiUnclusteredSub").textContent = all.unclustered > 0
            ? "Thêm sau lần huấn luyện gần nhất — chạy lại train_models.py để phân cụm"
            : "Mọi sản phẩm đều đã có cụm";
    }

    // ---------------------------------------------------------------- biểu đồ

    /** Nhãn trục cụm: màn hình hẹp rút gọn "Cụm 0" -> "C0" thay vì xoay chéo. */
    const clusterTicks = {
        maxRotation: 0, autoSkip: false,
        callback(v) { const l = this.getLabelForValue(v); return this.chart.width < 420 ? l.replace("Cụm ", "C") : l; }
    };

    function renderCharts(features) {
        const S = state.summary;
        const labels = S.map((s) => clusterName(s.cluster));
        const total = S.reduce((sum, s) => sum + s.product_count, 0);

        // (1) số sản phẩm theo cụm
        BP.chart("sizeChart", {
            type: "bar",
            data: { labels, datasets: [{ data: S.map((s) => s.product_count), backgroundColor: S.map((s) => clusterColor(s.cluster)) }] },
            options: {
                layout: { padding: { top: 18 } },
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (c) => `${BP.formatNumber(c.raw)} sản phẩm (${BP.formatPercent(pct(c.raw, total))})` } }
                },
                scales: { x: { grid: { display: false }, ticks: clusterTicks }, y: { beginAtZero: true, border: { display: false }, ticks: { callback: (v) => BP.formatNumber(v) } } }
            },
            plugins: [labelPlugin((chart) => chart.getDatasetMeta(0).data.map((el, i) =>
                ({ x: el.x, y: el.y - 4, text: BP.formatNumber(S[i].product_count) })))]
        });

        // (2) silhouette theo k; điểm k được chọn là dataset thứ 2 có 1 điểm
        const sel = features.model_selection || [];
        const chosenK = features.k;
        const chosen = sel.find((r) => r.k === chosenK);
        BP.chart("silChart", {
            type: "line",
            data: {
                labels: sel.map((r) => r.k),
                datasets: [
                    { label: "Silhouette", data: sel.map((r) => r.silhouette), borderColor: COLORS.series[0], backgroundColor: COLORS.series[0], tension: 0 },
                    { label: "k được chọn", data: sel.map((r) => (r.k === chosenK ? r.silhouette : null)), showLine: false,
                      pointRadius: 7, pointHoverRadius: 8, backgroundColor: COLORS.ink, borderColor: "#fff", borderWidth: 2 }
                ]
            },
            options: {
                interaction: { mode: "index", intersect: false },
                layout: { padding: { top: 10 } },
                plugins: {
                    legend: { position: "bottom" },
                    tooltip: { filter: (c) => c.raw !== null, callbacks: {
                        title: (items) => `k = ${items[0].label}`,
                        label: (c) => `${c.dataset.label}: ${BP.formatNumber(c.raw, "—", 3)}` } }
                },
                scales: {
                    x: { title: { display: true, text: "Số cụm k" }, grid: { display: false } },
                    y: { title: { display: true, text: "Silhouette" }, border: { display: false }, grace: "12%", ticks: { callback: (v) => BP.formatNumber(v, "—", 2) } }
                }
            },
            plugins: [labelPlugin((chart) => {
                const el = chart.getDatasetMeta(1).data[sel.findIndex((r) => r.k === chosenK)];
                return el && chosen ? [{ x: el.x, y: el.y - 12, text: `k = ${chosenK} · ${BP.formatNumber(chosen.silhouette, "—", 3)}` }] : [];
            })]
        });
        $("silNote").textContent = chosen
            ? `Silhouette (−1 đến 1) đo mức một sản phẩm gần cụm của nó hơn so với cụm khác; càng cao, các cụm càng tách bạch. `
              + `k = ${chosenK} cho silhouette cao nhất (${BP.formatNumber(chosen.silhouette, "—", 3)}) nên được chọn. `
              + `Mức ~${BP.formatNumber(chosen.silhouette, "—", 2)} là tách vừa phải — các cụm vẫn chồng lấn, nên đọc như nhóm tham khảo.`
            : "Chưa có kết quả chọn k.";

        // (3) bong bóng: giá trung vị vs mức giảm trung vị; cụm không tính được mức giảm thì bỏ qua và ghi chú
        const plotted = S.filter((s) => s.median_discount_percent !== null && s.median_price_vnd !== null);
        const missing = S.filter((s) => !plotted.includes(s));
        const maxCount = Math.max(...S.map((s) => s.product_count), 1);
        const radius = (n) => 6 + Math.sqrt(n / maxCount) * 24;
        BP.chart("bubbleChart", {
            type: "bubble",
            data: { datasets: plotted.map((s) => ({
                label: clusterName(s.cluster),
                data: [{ x: s.median_price_vnd, y: s.median_discount_percent, r: radius(s.product_count), n: s.product_count }],
                backgroundColor: clusterColor(s.cluster) + "b3", borderColor: "#fff", borderWidth: 2, hoverBorderColor: "#fff"
            })) },
            options: {
                layout: { padding: { right: 24 } },
                plugins: {
                    legend: { position: "bottom" },
                    tooltip: { callbacks: { label: (c) => [
                        `${c.dataset.label}: ${BP.formatNumber(c.raw.n)} sản phẩm`,
                        `Giá trung vị: ${BP.formatVnd(c.raw.x)}`,
                        `Giảm trung vị: ${BP.formatPercent(c.raw.y)}`] } }
                },
                scales: {
                    x: BP.vndAxis({ title: { display: true, text: "Giá trung vị" }, grace: "10%" }),
                    y: { title: { display: true, text: "Mức giảm trung vị (%)" }, grace: "15%", border: { display: false }, ticks: { callback: (v) => v + "%" } }
                }
            },
            plugins: [labelPlugin((chart) => chart.data.datasets.map((ds, i) => {
                const el = chart.getDatasetMeta(i).data[0];
                return { x: el.x + ds.data[0].r + 4, y: el.y, text: "C" + plotted[i].cluster, align: "left", baseline: "middle" };
            }))]
        });
        $("bubbleNote").textContent = missing.length
            ? `${missing.map((s) => clusterName(s.cluster)).join(", ")} không hiển thị: phần lớn sản phẩm không có giá niêm yết nên không tính được mức giảm.`
            : "";

        // (4) cơ cấu nhà bán lẻ (cột chồng 100%)
        const retailerIds = [...new Set(state.products.map((p) => p.retailer_id).filter(Boolean))].sort();
        BP.chart("retailerChart", {
            type: "bar",
            data: { labels, datasets: retailerIds.map((r) => ({
                label: retailerName(r),
                data: S.map((s) => pct(s.retailers.get(r) || 0, s.product_count)),
                counts: S.map((s) => s.retailers.get(r) || 0),
                backgroundColor: BP.retailerColor(r), borderColor: "#fff", borderWidth: { top: 1 }, borderRadius: 0
            })) },
            options: {
                plugins: {
                    legend: { position: "bottom" },
                    tooltip: { filter: (c) => c.raw > 0, callbacks: {
                        label: (c) => `${c.dataset.label}: ${BP.formatPercent(c.raw)} (${BP.formatNumber(c.dataset.counts[c.dataIndex])} SP)` } }
                },
                scales: {
                    x: { stacked: true, grid: { display: false }, ticks: clusterTicks },
                    y: { stacked: true, max: 100, border: { display: false }, ticks: { callback: (v) => v + "%" } }
                }
            }
        });
    }

    // ---------------------------------------------------------------- thẻ đặc điểm cụm

    function describe(s, base) {
        const parts = [];
        const ratio = s.median_price_vnd / base.price;
        parts.push(ratio >= 1.15 ? "Giá cao" : ratio <= 0.87 ? "Giá thấp" : "Giá trung bình");
        if (s.median_discount_percent === null) parts.push("hầu như không có giá niêm yết");
        else {
            const diff = s.median_discount_percent - base.discount;
            parts.push(diff >= 8 ? "giảm sâu" : diff <= -8 ? "giảm ít" : "giảm vừa");
        }
        const shop = `${s.retailerShare >= 50 ? "chủ yếu" : "nhiều nhất"} tại ${retailerName(s.top_retailer)}`;
        if (s.top_category === "Không rõ") parts.push(`${s.categoryShare >= 50 ? "phần lớn" : "nhiều"} sản phẩm chưa gắn danh mục, ${shop}`);
        else if (s.categoryShare >= 50 && s.retailerShare >= 50) parts.push(`chủ yếu ${s.top_category} tại ${retailerName(s.top_retailer)}`);
        else parts.push(`nhiều nhất ${s.top_category} (${BP.formatPercent(s.categoryShare, 0)}), ${shop}`);
        return parts.join(", ") + ".";
    }

    function renderCards() {
        const clustered = state.products.filter((p) => p.cluster !== null);
        const base = {
            price: BP.median(clustered.map((p) => p.current_price_vnd)),
            discount: BP.median(clustered.map((p) => p.discount_percent))
        };
        $("clusterCards").innerHTML = state.summary.map((s) => {
            const ratingNote = s.rating_missing_percent >= 50 ? ` <span class="muted">(thiếu ${BP.formatPercent(s.rating_missing_percent, 0)})</span>` : "";
            return `<article class="cluster-card">
                <h3>${clusterDot(s.cluster)}${esc(clusterName(s.cluster))}<span class="muted">${BP.formatNumber(s.product_count)} SP · ${BP.formatPercent(s.listing_share_percent)}</span></h3>
                <p class="desc">${esc(describe(s, base))}</p>
                <dl class="cluster-stats">
                    <dt>Giá trung vị</dt><dd>${BP.formatVnd(s.median_price_vnd)}</dd>
                    <dt>Giảm trung vị</dt><dd>${BP.formatPercent(s.median_discount_percent)}</dd>
                    <dt>Rating trung vị</dt><dd>${BP.formatRating(s.median_rating)}${ratingNote}</dd>
                    <dt>Danh mục nổi bật</dt><dd>${esc(s.top_category)} <span class="muted">${BP.formatPercent(s.categoryShare, 0)}</span></dd>
                    <dt>Nhà bán lẻ nổi bật</dt><dd>${esc(retailerName(s.top_retailer))} <span class="muted">${BP.formatPercent(s.retailerShare, 0)}</span></dd>
                </dl>
            </article>`;
        }).join("") || BP.stateHtml("Chưa có kết quả phân cụm.");
    }

    // ---------------------------------------------------------------- đặc trưng + nhận định

    function renderFeatures(info) {
        const features = info.data || [];
        const group = (type, title) => {
            const items = features.filter((f) => f.type === type);
            return items.length ? `<div class="feature-group"><span class="field-label">${title}</span><div class="chips">${
                items.map((f) => `<span class="badge ${type === "numeric" ? "badge-info" : "badge-brand"}">${esc(f.label)}</span>`).join("")}</div></div>` : "";
        };
        $("featureList").innerHTML = group("numeric", "Biến số") + group("categorical", "Biến phân loại") || BP.stateHtml("Không có thông tin đặc trưng.");
        const sel = info.model_selection || [];
        $("modelTiles").innerHTML = [
            ["Số cụm đã thử", sel.length ? `${sel[0].k}–${sel[sel.length - 1].k}` : "—"],
            ["k được chọn", BP.formatNumber(info.k)],
            ["Silhouette", BP.formatNumber(info.silhouette, "—", 3)]
        ].map(([label, value]) => `<div class="stat-tile"><div class="label">${label}</div><div class="value">${value}</div></div>`).join("");
    }

    function renderInsights(features) {
        const S = state.summary;
        if (!S.length) { $("insights").innerHTML = ""; return; }
        const items = [];
        const big = extremes(S, "product_count");
        items.push(`${superlative(big, "lớn nhất")} với ${BP.formatNumber(big[0].product_count)} sản phẩm (${BP.formatPercent(big[0].listing_share_percent)}); `
            + `${superlative(extremes(S, "product_count", -1), "nhỏ nhất")} chỉ ${BP.formatPercent(extremes(S, "product_count", -1)[0].listing_share_percent)}.`);

        const hi = extremes(S, "median_price_vnd"), lo = extremes(S, "median_price_vnd", -1);
        const spread = hi[0].median_price_vnd / lo[0].median_price_vnd;
        items.push(`Giá trung vị dao động từ ${BP.formatVnd(lo[0].median_price_vnd)} (${nameList(lo)}) đến ${BP.formatVnd(hi[0].median_price_vnd)} (${nameList(hi)})`
            + (spread < 2 ? ` — chênh chưa tới 2 lần, nên mức giảm, danh mục và nhà bán lẻ tách các cụm rõ hơn giá.` : ` — chênh ${BP.formatNumber(spread, "—", 1)} lần.`));

        const deep = extremes(S, "median_discount_percent");
        const noListed = S.filter((s) => s.median_discount_percent === null);
        if (deep.length) items.push(`${superlative(deep, "có mức giảm trung vị sâu nhất")} (${BP.formatPercent(deep[0].median_discount_percent)})`
            + (noListed.length ? `; ${nameList(noListed)} gần như không có giá niêm yết nên không tính được mức giảm.` : "."));

        const dominated = S.filter((s) => s.retailerShare >= 80);
        if (dominated.length) items.push(`${nameList(dominated)} có trên 80% sản phẩm từ một nhà bán lẻ — cách mỗi sàn ghi dữ liệu (giá niêm yết, rating) ảnh hưởng mạnh tới kết quả phân cụm.`);
        else if (features.silhouette !== null && features.silhouette !== undefined) {
            items.push(`Silhouette ${BP.formatNumber(features.silhouette, "—", 3)} cho thấy các cụm tách biệt ở mức vừa phải.`);
        }
        $("insights").innerHTML = items.slice(0, 4).map((t, i) => `<li><span class="ins-no">${i + 1}</span><span>${t}</span></li>`).join("");
    }

    // ---------------------------------------------------------------- bảng sản phẩm

    function setupTable(hasUnclustered) {
        $("clusterFilter").insertAdjacentHTML("beforeend", state.summary.map((s) =>
            `<option value="${s.cluster}">${esc(clusterName(s.cluster))} (${BP.formatNumber(s.product_count)})</option>`).join("")
            + (hasUnclustered ? `<option value="${NONE}">Chưa phân cụm</option>` : ""));
        $("clusterFilter").addEventListener("change", () => { state.page = 1; renderTable(); });
        $("searchInput").addEventListener("input", BP.debounce(() => { state.page = 1; renderTable(); }, 200));
        renderTable();
    }

    function filtered() {
        const c = $("clusterFilter").value;
        const q = BP.normalizeText($("searchInput").value);
        return state.products.filter((p) =>
            (c === "" || (c === NONE ? p.cluster === null : p.cluster === Number(c)))
            && (!q || BP.normalizeText(`${p.product_name} ${p.brand}`).includes(q)));
    }

    function renderTable() {
        const list = filtered();
        const pages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
        state.page = Math.min(state.page, pages);
        const rows = list.slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE);
        $("productBody").innerHTML = rows.length ? rows.map((p) => `<tr>
                <td class="name-cell">${esc(p.product_name)}</td>
                <td>${esc(p.brand || "—")}</td>
                <td class="nowrap">${esc(p.source || retailerName(p.retailer_id))}</td>
                <td>${esc(p.primary_category || "—")}</td>
                <td class="num nowrap">${BP.formatVnd(p.current_price_vnd)}</td>
                <td class="num">${BP.formatPercent(p.discount_percent)}</td>
                <td><span class="badge">${clusterDot(p.cluster)}${esc(clusterName(p.cluster))}</span></td>
            </tr>`).join("")
            : `<tr><td colspan="7">${BP.stateHtml("Không có sản phẩm phù hợp bộ lọc.")}</td></tr>`;
        $("tableInfo").textContent = `${BP.formatNumber(list.length)} sản phẩm phù hợp`;
        $("pageInfo").textContent = list.length
            ? `Hiển thị ${BP.formatNumber((state.page - 1) * PAGE_SIZE + 1)}–${BP.formatNumber((state.page - 1) * PAGE_SIZE + rows.length)} / ${BP.formatNumber(list.length)}`
            : "";
        BP.renderPagination($("pagination"), state.page, pages, (page) => { state.page = page; renderTable(); });
    }

    document.addEventListener("DOMContentLoaded", load);
    BP.onProductsUpdated(() => location.reload());
})();
