/* batthuong.js - trang Phát hiện bất thường (Isolation Forest). Dữ liệu: GET /api/anomalies. */
(function () {
    "use strict";

    const { COLORS, escapeHtml: esc } = BP;
    const $ = (id) => document.getElementById(id);
    const PAGE_SIZE = 50;
    const NO_CATEGORY = "__none";
    const FEATURE_LABELS = {
        price_log: "Giá bán (log)", price_vs_category: "Giá so với trung vị danh mục", discount: "Mức giảm giá (%)",
        listed_ratio: "Giá niêm yết / giá bán (log)", rating: "Rating", review_count_log: "Số lượt đánh giá (log)"
    };

    const state = { products: [], page: 1 };

    const retailerName = (id) => BP.RETAILER_NAMES[BP.retailerKey(id)] || id || "—";
    const retailerDot = (id) => `<span class="dot ${BP.RETAILER_NAMES[BP.retailerKey(id)] ? "rt-" + BP.retailerKey(id) : "rt-other"}"></span>`;
    const reasonsOf = (p) => (p.reason || "").split("; ").map((r) => r.trim()).filter(Boolean);
    const pct = (part, total) => (total ? (part / total) * 100 : null);
    const priceRatio = (p) => (p.category_median_price > 0 && p.current_price_vnd > 0 ? p.current_price_vnd / p.category_median_price : null);
    const countBy = (items, keyFn) => items.reduce((m, x) => { for (const k of [].concat(keyFn(x))) m.set(k, (m.get(k) || 0) + 1); return m; }, new Map());

    /** Plugin vẽ nhãn trực tiếp (chữ màu mực). getLabels(chart) -> [{x, y, text, align, baseline}]. */
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

    /** Các mục [khóa, giá trị] có giá trị lớn nhất (giữ tất cả khi hòa). */
    function topEntries(entries) {
        if (!entries.length) return [];
        const best = Math.max(...entries.map((e) => e[1]));
        return entries.filter((e) => Math.abs(e[1] - best) < 1e-9);
    }

    // ---------------------------------------------------------------- tải dữ liệu

    async function load() {
        document.querySelectorAll("[data-icon]").forEach((el) => el.insertAdjacentHTML("afterbegin", BP.icon(el.dataset.icon)));
        $("productBody").innerHTML = `<tr><td colspan="9">${BP.stateHtml("Đang tải...", "loading")}</td></tr>`;
        try {
            const data = await BP.api("/api/anomalies");
            state.products = (data.products || []).slice().sort((a, b) => a.anomaly_score - b.anomaly_score);
            const model = data.model || {};
            const stats = computeStats(state.products);
            renderKpis(data, model, stats);
            renderCharts(stats);
            renderModel(model, data.total);
            setupTable(stats);
            $("trainedAt").textContent = `Huấn luyện: ${BP.formatDate(data.trained_at, true)}`;
        } catch (err) {
            $("pageError").innerHTML = `<div class="notice notice-bad">${BP.icon("alert")}<span>${esc(err.message)}</span></div>`;
            $("pageError").classList.add("mt");
            $("productBody").innerHTML = `<tr><td colspan="9">${BP.stateHtml(err.message, "error")}</td></tr>`;
            $("exportBtn").disabled = true;
        }
    }

    function computeStats(products) {
        const flagged = products.filter((p) => p.is_anomaly);
        const totals = countBy(products, (p) => p.retailer_id);
        const bad = countBy(flagged, (p) => p.retailer_id);
        const retailers = [...totals].map(([id, total]) => ({ id, total, flagged: bad.get(id) || 0, rate: pct(bad.get(id) || 0, total) }))
            .sort((a, b) => b.rate - a.rate || b.total - a.total);
        const reasons = [...countBy(flagged, reasonsOf)].sort((a, b) => b[1] - a[1]);
        return { flagged, retailers, reasons };
    }

    // ---------------------------------------------------------------- KPI

    function renderKpis(data, model, stats) {
        const total = data.total ?? state.products.length;
        $("kpiFlagged").textContent = BP.formatNumber(stats.flagged.length);
        $("kpiFlaggedSub").textContent = `${BP.formatPercent(pct(stats.flagged.length, total))} trên ${BP.formatNumber(total)} SP đã chấm điểm`;
        $("kpiContamination").textContent = BP.formatPercent((BP.toNumber(model.contamination) ?? NaN) * 100, 0);

        const topReasons = topEntries(stats.reasons);
        $("kpiReason").textContent = topReasons.map((e) => e[0]).join(" / ") || "—";
        $("kpiReasonSub").textContent = topReasons.length
            ? `${BP.formatNumber(topReasons[0][1])} SP (${BP.formatPercent(pct(topReasons[0][1], stats.flagged.length), 0)} số SP bất thường)${topReasons.length > 1 ? " mỗi lý do" : ""}`
            : "—";

        const topShops = topEntries(stats.retailers.map((r) => [r, r.rate]));
        $("kpiRetailer").textContent = topShops.map((e) => retailerName(e[0].id)).join(" / ") || "—";
        $("kpiRetailerSub").textContent = topShops.length
            ? `${BP.formatPercent(topShops[0][0].rate)} (${BP.formatNumber(topShops[0][0].flagged)}/${BP.formatNumber(topShops[0][0].total)} SP)`
            : "—";
    }

    // ---------------------------------------------------------------- biểu đồ

    /** Nhãn trục dài (vd "The Gioi Skin Food") tách 2 dòng thay vì xoay chéo. */
    const wrapLabel = (text, max = 10) => {
        const words = String(text).split(" ");
        if (text.length <= max || words.length < 2) return text;
        const half = Math.ceil(words.length / 2);
        return [words.slice(0, half).join(" "), words.slice(half).join(" ")];
    };

    /** Trục log chỉ giữ mốc 1-2-5 (10k, 20k, 50k, 100k...) cho dễ đọc. */
    const logTicks = (axis) => {
        axis.ticks = axis.ticks.filter((t) => {
            const m = t.value / 10 ** Math.floor(Math.log10(t.value));
            return [1, 2, 5].some((k) => Math.abs(m - k) < 1e-6);
        });
    };

    function renderCharts(stats) {
        // (1) phân tán giá - mức giảm: chỉ vẽ SP có giá niêm yết (mới tính được % giảm)
        const plottable = state.products.filter((p) => p.current_price_vnd > 0 && p.discount_percent !== null);
        const point = (p) => ({ x: p.current_price_vnd, y: p.discount_percent, p });
        BP.chart("scatterChart", {
            type: "scatter",
            data: { datasets: [
                { label: "Bình thường", data: plottable.filter((p) => !p.is_anomaly).map(point), order: 2,
                  backgroundColor: COLORS.muted + "59", borderWidth: 0, pointRadius: 2, pointHoverRadius: 4 },
                { label: "Bất thường", data: plottable.filter((p) => p.is_anomaly).map(point), order: 1,
                  backgroundColor: COLORS.status.bad + "cc", borderColor: "#fff", borderWidth: 1, pointRadius: 3.5, pointHoverRadius: 6, pointStyle: "triangle" }
            ] },
            options: {
                plugins: {
                    legend: { position: "bottom" },
                    tooltip: { callbacks: {
                        title: (items) => { const n = items[0].raw.p.product_name || ""; return n.length > 60 ? n.slice(0, 58) + "…" : n; },
                        label: (c) => {
                            const p = c.raw.p;
                            return [`${retailerName(p.retailer_id)} · ${BP.formatVnd(p.current_price_vnd)} · giảm ${BP.formatPercent(p.discount_percent)}`]
                                .concat(p.is_anomaly ? [`Lý do: ${p.reason || "—"}`] : []);
                        } } }
                },
                scales: {
                    x: BP.vndAxis({ type: "logarithmic", afterBuildTicks: logTicks, title: { display: true, text: "Giá bán (thang log)" } }),
                    y: { min: 0, max: 100, title: { display: true, text: "Mức giảm (%)" }, border: { display: false }, ticks: { callback: (v) => v + "%" } }
                }
            }
        });
        const hidden = state.products.length - plottable.length;
        const hiddenBad = stats.flagged.filter((p) => !plottable.includes(p)).length;
        $("scatterNote").textContent = hidden
            ? `${BP.formatNumber(hidden)} sản phẩm không có giá niêm yết (không tính được % giảm) không hiển thị, trong đó ${BP.formatNumber(hiddenBad)} sản phẩm bất thường.`
            : "";

        // (2) tỷ lệ bất thường theo nhà bán lẻ
        const R = stats.retailers;
        BP.chart("retailerChart", {
            type: "bar",
            data: { labels: R.map((r) => wrapLabel(retailerName(r.id))), datasets: [{ data: R.map((r) => r.rate), backgroundColor: R.map((r) => BP.retailerColor(r.id)) }] },
            options: {
                layout: { padding: { top: 18 } },
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (c) => `${BP.formatPercent(c.raw)} · ${BP.formatNumber(R[c.dataIndex].flagged)}/${BP.formatNumber(R[c.dataIndex].total)} sản phẩm` } }
                },
                scales: { x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: false } },
                          y: { beginAtZero: true, border: { display: false }, ticks: { callback: (v) => v + "%" } } }
            },
            plugins: [labelPlugin((chart) => chart.getDatasetMeta(0).data.map((el, i) => ({ x: el.x, y: el.y - 4, text: BP.formatPercent(R[i].rate) })))]
        });

        // (3) lý do bất thường (cột ngang)
        const reasons = stats.reasons;
        BP.chart("reasonChart", {
            type: "bar",
            data: { labels: reasons.map((r) => r[0]), datasets: [{ data: reasons.map((r) => r[1]), backgroundColor: COLORS.series[0] }] },
            options: {
                indexAxis: "y",
                layout: { padding: { right: 36 } },
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (c) => `${BP.formatNumber(c.raw)} sản phẩm (${BP.formatPercent(pct(c.raw, stats.flagged.length))} số SP bất thường)` } }
                },
                scales: { y: { grid: { display: false }, ticks: { callback(v) { const l = this.getLabelForValue(v); return this.chart.width < 480 ? wrapLabel(l, 14) : l; } } },
                          x: { beginAtZero: true, border: { display: false }, ticks: { callback: (v) => BP.formatNumber(v) } } }
            },
            plugins: [labelPlugin((chart) => chart.getDatasetMeta(0).data.map((el, i) =>
                ({ x: el.x + 6, y: el.y, text: BP.formatNumber(reasons[i][1]), align: "left", baseline: "middle" })))]
        });
    }

    // ---------------------------------------------------------------- mô hình

    function renderModel(model, total) {
        $("modelName").textContent = `${model.name || "Isolation Forest"} · contamination ${BP.formatPercent((model.contamination ?? NaN) * 100, 0)}`;
        $("featureList").innerHTML = (model.features || []).map((f) => `<span class="badge badge-info">${esc(FEATURE_LABELS[f] || f)}</span>`).join("")
            || '<span class="muted">—</span>';
        $("sensitivityBody").innerHTML = (model.sensitivity || []).map((s) => `<tr>
                <td class="nowrap">${BP.formatPercent(s.contamination * 100, 0)}${Math.abs(s.contamination - model.contamination) < 1e-9 ? ' <span class="badge badge-brand">Đang dùng</span>' : ""}</td>
                <td class="num">${BP.formatNumber(s.flagged)}</td>
                <td class="num">${BP.formatPercent(pct(s.flagged, total))}</td>
            </tr>`).join("") || `<tr><td colspan="3" class="muted">Không có dữ liệu độ nhạy.</td></tr>`;
    }

    // ---------------------------------------------------------------- bảng

    function setupTable(stats) {
        const options = (entries) => entries.map(([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join("");
        $("retailerFilter").insertAdjacentHTML("beforeend", options(stats.retailers.map((r) => [r.id, retailerName(r.id)])
            .sort((a, b) => a[1].localeCompare(b[1], "vi"))));
        const categories = [...new Set(state.products.map((p) => p.category).filter(Boolean))].sort((a, b) => a.localeCompare(b, "vi"));
        $("categoryFilter").insertAdjacentHTML("beforeend", options(categories.map((c) => [c, c]))
            + (state.products.some((p) => !p.category) ? options([[NO_CATEGORY, "Không rõ"]]) : ""));
        $("reasonFilter").insertAdjacentHTML("beforeend", options(stats.reasons.map(([r, n]) => [r, `${r} (${BP.formatNumber(n)})`])));

        const refresh = () => { state.page = 1; renderTable(); };
        for (const id of ["modeFilter", "retailerFilter", "categoryFilter", "reasonFilter"]) $(id).addEventListener("change", refresh);
        $("searchInput").addEventListener("input", BP.debounce(refresh, 200));
        $("exportBtn").addEventListener("click", exportCsv);
        renderTable();
    }

    function filtered() {
        const mode = $("modeFilter").value, shop = $("retailerFilter").value, cat = $("categoryFilter").value, reason = $("reasonFilter").value;
        const q = BP.normalizeText($("searchInput").value);
        return state.products.filter((p) =>
            (mode === "all" || p.is_anomaly)
            && (!shop || p.retailer_id === shop)
            && (!cat || (cat === NO_CATEGORY ? !p.category : p.category === cat))
            && (!reason || reasonsOf(p).includes(reason))
            && (!q || BP.normalizeText(`${p.product_name} ${p.brand}`).includes(q)));
    }

    function row(p) {
        const url = BP.safeUrl(p.product_url);
        const name = url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(p.product_name)}</a>` : esc(p.product_name);
        const ratio = priceRatio(p);
        const score = BP.formatNumber(p.anomaly_score, "—", 3);
        return `<tr>
            <td class="name-cell">${name}<small>${esc(p.brand || "—")}</small></td>
            <td><span class="shop">${retailerDot(p.retailer_id)}${esc(retailerName(p.retailer_id))}</span></td>
            <td>${esc(p.category || "Không rõ")}</td>
            <td class="num nowrap">${BP.formatVnd(p.current_price_vnd)}${ratio === null ? ""
                : `<small class="ratio ${ratio >= 2 || ratio <= 0.5 ? "high" : ""}">${ratio >= 1
                    ? `gấp ${BP.formatNumber(ratio, "—", 1)} lần` : `bằng ${BP.formatPercent(ratio * 100, 0)}`} trung vị DM</small>`}</td>
            <td class="num nowrap">${BP.formatVnd(p.listed_price_vnd)}</td>
            <td class="num">${BP.formatPercent(p.discount_percent)}</td>
            <td class="num">${BP.formatRating(p.rating)}</td>
            <td><div class="score">${p.is_anomaly ? `<span class="badge badge-bad">${BP.icon("anomaly")}Bất thường</span>` : ""}<small>${score}</small></div></td>
            <td class="reason">${esc(p.reason || "—")}</td>
        </tr>`;
    }

    function renderTable() {
        const list = filtered();
        const pages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
        state.page = Math.min(state.page, pages);
        const start = (state.page - 1) * PAGE_SIZE;
        const rows = list.slice(start, start + PAGE_SIZE);
        $("productBody").innerHTML = rows.length ? rows.map(row).join("")
            : `<tr><td colspan="9">${BP.stateHtml("Không có sản phẩm phù hợp bộ lọc.")}</td></tr>`;
        const flagged = list.filter((p) => p.is_anomaly).length;
        $("tableInfo").textContent = `${BP.formatNumber(list.length)} sản phẩm (${BP.formatNumber(flagged)} bất thường) · sắp theo điểm bất thường tăng dần (bất thường nhất trước)`;
        $("pageInfo").textContent = list.length ? `Hiển thị ${BP.formatNumber(start + 1)}–${BP.formatNumber(start + rows.length)} / ${BP.formatNumber(list.length)}` : "";
        $("exportBtn").disabled = !list.length;
        BP.renderPagination($("pagination"), state.page, pages, (page) => { state.page = page; renderTable(); });
    }

    function exportCsv() {
        const list = filtered();
        const rows = [["Mã SP", "Tên sản phẩm", "Thương hiệu", "Nhà bán lẻ", "Danh mục", "Giá bán (VND)", "Giá niêm yết (VND)", "Giảm (%)",
            "Rating", "Số đánh giá", "Trung vị giá danh mục (VND)", "Điểm bất thường", "Bất thường", "Lý do"]];
        for (const p of list) {
            rows.push([p.product_id, p.product_name, p.brand, retailerName(p.retailer_id), p.category || "Không rõ", p.current_price_vnd, p.listed_price_vnd,
                p.discount_percent, p.rating, p.review_count, p.category_median_price, p.anomaly_score?.toFixed(4), p.is_anomaly ? "Có" : "Không", p.reason]);
        }
        BP.downloadCsv(`bat-thuong-${new Date().toISOString().slice(0, 10)}.csv`, rows);
        BP.toast(`Đã xuất ${BP.formatNumber(list.length)} dòng CSV.`);
    }

    document.addEventListener("DOMContentLoaded", load);
})();
