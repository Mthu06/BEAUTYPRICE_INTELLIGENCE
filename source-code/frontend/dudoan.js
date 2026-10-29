/* dudoan.js - trang "Dự đoán giá": hồi quy giá bán + phân loại phân khúc giá (đánh giá trên tập test). */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const esc = BP.escapeHtml;
    const C = BP.COLORS;
    const GRAY = "#c3c7d3";
    const PAGE_SIZE = 50;
    const SEG_CLASS = { "Thấp": "seg-low", "Trung bình": "seg-mid", "Cao": "seg-high" };
    const FEATURE_LABELS = {
        brand: "Thương hiệu", category: "Danh mục", retailer_id: "Nhà bán lẻ", product_type: "Loại SP", rating: "Rating",
        review_count_log: "Số lượt đánh giá (log)", volume_ml_log: "Dung tích", weight_g_log: "Khối lượng",
        pack_count: "Số món", is_combo: "Combo", category_count: "Số danh mục"
    };
    const SORTS = {
        apeDesc: (a, b) => b.absolute_percentage_error - a.absolute_percentage_error,
        apeAsc: (a, b) => a.absolute_percentage_error - b.absolute_percentage_error,
        aeDesc: (a, b) => b.absolute_error_vnd - a.absolute_error_vnd,
        priceDesc: (a, b) => b.current_price_vnd - a.current_price_vnd,
        name: (a, b) => a.product_name.localeCompare(b.product_name, "vi")
    };

    const state = { data: null, rows: [], filtered: [], page: 1 };

    const ratio = (v, digits = 1) => BP.formatPercent(BP.toNumber(v) === null ? null : v * 100, digits);
    const alpha = (hex, a) => hex + Math.round(a * 255).toString(16).padStart(2, "0");
    const seg = (label) => label ? `<span class="seg ${SEG_CLASS[label] || ""}">${esc(label)}</span>` : "—";
    const isRight = (r) => r.classified_price_group === r.actual_price_group;
    const shortName = (s, n = 60) => (s = String(s || "")).length > n ? s.slice(0, n - 1) + "…" : s;
    /** "Random Forest Regressor" -> ["Random Forest", "Regressor"] để nhãn trục không bị chồng. */
    const wrap = (text, max = innerWidth < 600 ? 9 : 16) => String(text).split(" ").reduce((lines, word) => {
        const last = lines[lines.length - 1];
        if (last && (last + " " + word).length <= max) lines[lines.length - 1] = last + " " + word; else lines.push(word);
        return lines;
    }, []);

    /** Plugin nhỏ: ghi giá trị ở đầu mỗi cột (chữ màu chữ, không dùng màu chuỗi). */
    const valueLabels = (format) => ({
        id: "valueLabels",
        afterDatasetsDraw(chart) {
            const { ctx } = chart;
            const horizontal = chart.options.indexAxis === "y";
            ctx.save();
            ctx.font = `600 11px ${Chart.defaults.font.family}`;
            ctx.fillStyle = C.ink2;
            ctx.textAlign = horizontal ? "left" : "center";
            ctx.textBaseline = horizontal ? "middle" : "bottom";
            chart.data.datasets.forEach((ds, i) => chart.getDatasetMeta(i).data.forEach((bar, j) => {
                const text = format(ds.data[j]);
                if (text) ctx.fillText(text, horizontal ? bar.x + 6 : bar.x, horizontal ? bar.y : bar.y - 4);
            }));
            ctx.restore();
        }
    });

    const loaded = (id) => document.getElementById(id)?.parentElement.classList.remove("is-loading");

    // ---------------------------------------------------------------- phần 1: hồi quy

    function renderRegression(d) {
        const m = d.metrics || {};
        const apes = state.rows.map((r) => r.absolute_percentage_error);
        $("regModel").textContent = `Mô hình được chọn: ${m.model || "—"} · huấn luyện lúc ${BP.formatDate(d.trained_at, true)} · ${BP.formatNumber(state.rows.length)} sản phẩm tập test`;
        $("kpiMae").textContent = BP.formatVnd(m.mae);
        $("kpiRmse").textContent = BP.formatVnd(m.rmse);
        $("kpiR2").textContent = BP.formatNumber(m.r2, "—", 3);
        $("kpiR2Sub").textContent = m.r2 == null ? "—" : `Giải thích ~${ratio(m.r2, 0)} biến thiên giá`;
        $("kpiMape").textContent = BP.formatPercent(m.mape);
        $("kpiMapeSub").textContent = `Trung vị sai số %: ${BP.formatPercent(BP.median(apes))}`;

        drawScatter();
        drawCompare("regCompareChart", d.model_comparison, "mae", BP.formatVndShort,
            (v) => [`MAE: ${BP.formatVnd(v.mae)}`, `RMSE: ${BP.formatVnd(v.rmse)}`, `R²: ${BP.formatNumber(v.r2, "—", 3)}`, `MAPE: ${BP.formatPercent(v.mape)}`]);
        drawFeatures();
        drawGroups();
    }

    function drawScatter() {
        const points = state.rows.filter((r) => r.current_price_vnd > 0 && r.predicted_price_vnd > 0).map((r) => ({
            x: r.current_price_vnd, y: r.predicted_price_vnd, name: r.product_name, ape: r.absolute_percentage_error
        }));
        if (!points.length) return;
        const all = points.flatMap((p) => [p.x, p.y]);
        const lo = Math.min(...all), hi = Math.max(...all);
        // trục log chỉ ghi nhãn ở các mốc 1-2-5 x 10^n cho gọn
        const nice = (v) => { const m = v / 10 ** Math.floor(Math.log10(v)); return [1, 2, 5].some((k) => Math.abs(m - k) < 1e-6); };
        const axis = (title) => ({
            type: "logarithmic", min: lo * 0.85, max: hi * 1.15,
            title: { display: true, text: title, color: C.ink2 },
            ticks: { autoSkip: false, maxRotation: 0, callback: (v) => nice(v) ? BP.formatVndShort(v) : "" },
            grid: { color: (c) => nice(c.tick.value) ? C.grid : "transparent" }, border: { display: false }
        });
        BP.chart("scatterChart", {
            type: "scatter",
            data: {
                datasets: [
                    { label: "Sản phẩm tập test", data: points, backgroundColor: alpha(C.series[0], 0.45), borderWidth: 0, pointRadius: 2.5, pointHoverRadius: 5 },
                    { type: "line", label: "Dự đoán đúng tuyệt đối (y = x)", data: [{ x: lo, y: lo }, { x: hi, y: hi }],
                      borderColor: C.ink2, borderWidth: 1.5, borderDash: [6, 4], pointStyle: "line", pointRadius: 0, pointHitRadius: 0, fill: false }
                ]
            },
            options: {
                scales: { x: axis("Giá thực tế"), y: axis("Giá dự đoán") },
                plugins: {
                    legend: { position: "bottom" },
                    tooltip: {
                        filter: (item) => item.datasetIndex === 0,
                        callbacks: {
                            title: (items) => shortName(items[0].raw.name),
                            label: (item) => [`Thực tế: ${BP.formatVnd(item.raw.x)}`, `Dự đoán: ${BP.formatVnd(item.raw.y)}`, `Sai số: ${BP.formatPercent(item.raw.ape)}`]
                        }
                    }
                }
            }
        });
        loaded("scatterChart");
    }

    /** Cột so sánh mô hình theo một chỉ số validation: mô hình được chọn tô màu, còn lại xám. */
    function drawCompare(id, runs, key, format, tooltipLines) {
        const list = (runs || []).filter((r) => BP.toNumber(r.metrics?.validation?.[key]) !== null);
        if (!list.length) { $(id).parentElement.innerHTML = BP.stateHtml("Chưa có kết quả so sánh mô hình."); return; }
        const selected = list.findIndex((r) => r.is_selected);
        BP.chart(id, {
            type: "bar",
            data: {
                labels: list.map((r) => r.is_selected ? [...wrap(r.model_name), "★ Được chọn"] : wrap(r.model_name)),
                datasets: [{ label: key.toUpperCase(), data: list.map((r) => r.metrics.validation[key]), backgroundColor: list.map((r) => r.is_selected ? C.series[0] : GRAY) }]
            },
            options: {
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { title: (items) => list[items[0].dataIndex].model_name, label: (item) => tooltipLines(list[item.dataIndex].metrics.validation) } }
                },
                scales: {
                    x: { grid: { display: false }, ticks: { autoSkip: false, maxRotation: 0, color: (c) => c.index === selected ? C.ink : C.muted,
                         font: (c) => ({ weight: c.index === selected ? "700" : "400" }) } },
                    y: { beginAtZero: true, grace: "12%", ticks: { callback: format }, grid: { color: C.grid }, border: { display: false } }
                }
            },
            plugins: [valueLabels(format)]
        });
        loaded(id);
    }

    function drawFeatures() {
        const list = state.data.feature_importance?.[$("featureTask").value] || [];
        if (!list.length) { $("featureChart").parentElement.innerHTML = BP.stateHtml("Chưa có dữ liệu mức độ quan trọng."); return; }
        BP.chart("featureChart", {
            type: "bar",
            data: { labels: list.map((f) => FEATURE_LABELS[f.feature] || f.feature), datasets: [{ data: list.map((f) => f.importance * 100), backgroundColor: C.series[0] }] },
            options: {
                indexAxis: "y",
                plugins: { legend: { display: false }, tooltip: { callbacks: { label: (item) => `Mức quan trọng: ${BP.formatPercent(item.raw)}` } } },
                scales: {
                    x: { beginAtZero: true, grace: "14%", ticks: { callback: (v) => v + "%" }, grid: { color: C.grid }, border: { display: false } },
                    y: { grid: { display: false }, ticks: { color: C.ink2 } }
                }
            },
            plugins: [valueLabels((v) => BP.formatPercent(v))]
        });
        loaded("featureChart");
    }

    /** MAPE theo nhóm giá thực tế. Trả về danh sách nhóm để dùng cho nhận định. */
    function groupStats() {
        return Object.keys(SEG_CLASS).map((label) => {
            const apes = state.rows.filter((r) => r.actual_price_group === label).map((r) => r.absolute_percentage_error);
            return { label, n: apes.length, mape: BP.average(apes), median: BP.median(apes) };
        }).filter((g) => g.n);
    }

    function drawGroups() {
        const groups = groupStats();
        if (!groups.length) return;
        BP.chart("groupChart", {
            type: "bar",
            data: {
                labels: groups.map((g) => [g.label, `n = ${BP.formatNumber(g.n)}`]),
                datasets: [{ label: "MAPE", data: groups.map((g) => g.mape), backgroundColor: groups.map((g) => C.segment[g.label]) }]
            },
            options: {
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { title: (items) => `Nhóm ${groups[items[0].dataIndex].label}`,
                        label: (item) => [`MAPE: ${BP.formatPercent(item.raw)}`, `Trung vị sai số: ${BP.formatPercent(groups[item.dataIndex].median)}`] } }
                },
                scales: {
                    x: { grid: { display: false }, ticks: { color: C.ink2 } },
                    y: { beginAtZero: true, grace: "12%", ticks: { callback: (v) => v + "%" }, grid: { color: C.grid }, border: { display: false } }
                }
            },
            plugins: [valueLabels((v) => BP.formatPercent(v))]
        });
        loaded("groupChart");
        const best = groups.reduce((a, b) => (b.mape < a.mape ? b : a));
        const worst = groups.reduce((a, b) => (b.mape > a.mape ? b : a));
        $("groupNote").innerHTML = `Nhóm <b>${esc(best.label)}</b> được dự đoán chính xác nhất (MAPE ${BP.formatPercent(best.mape)}); ` +
            `nhóm <b>${esc(worst.label)}</b> sai lệch nhiều nhất (${BP.formatPercent(worst.mape)}).`;
    }

    // ---------------------------------------------------------------- phần 2: phân loại

    function renderClassification(d) {
        const c = d.classification;
        if (!c) {
            $("clfModel").textContent = "Chưa có kết quả mô hình phân loại.";
            $("confusion").innerHTML = BP.stateHtml("Chưa có kết quả mô hình phân loại.");
            $("clfCompareChart").parentElement.innerHTML = BP.stateHtml("Chưa có kết quả.");
            return;
        }
        $("clfModel").textContent = `Mô hình được chọn: ${c.model} · dự đoán nhóm Thấp / Trung bình / Cao từ đặc trưng sản phẩm (không dùng giá)`;
        $("kpiAcc").textContent = ratio(c.accuracy);
        $("kpiF1").textContent = BP.formatNumber(c.f1_macro, "—", 3);
        $("kpiPrec").textContent = BP.formatNumber(c.precision_macro, "—", 3);
        $("kpiRec").textContent = BP.formatNumber(c.recall_macro, "—", 3);
        renderConfusion(c.confusion_matrix);
        drawCompare("clfCompareChart", c.comparison, "f1_macro", (v) => BP.formatNumber(v, "—", 3),
            (v) => [`F1-macro: ${BP.formatNumber(v.f1_macro, "—", 3)}`, `Accuracy: ${ratio(v.accuracy)}`,
                `Precision: ${BP.formatNumber(v.precision_macro, "—", 3)}`, `Recall: ${BP.formatNumber(v.recall_macro, "—", 3)}`]);

        const t = d.thresholds || {};
        $("thresholdNote").innerHTML = t.q1_vnd == null ? "" :
            `Ngưỡng phân khúc (phân vị 1/3 và 2/3 giá tập train): ${seg("Thấp")} ≤ <b>${BP.formatVnd(t.q1_vnd)}</b> &lt; ${seg("Trung bình")} ≤ <b>${BP.formatVnd(t.q2_vnd)}</b> &lt; ${seg("Cao")}`;
    }

    function renderConfusion(cm) {
        if (!cm?.matrix?.length) { $("confusion").innerHTML = BP.stateHtml("Không có ma trận nhầm lẫn."); return; }
        const { labels, matrix } = cm;
        const level = (t) => [0.1, 0.2, 0.35, 0.5, 0.7].filter((x) => t >= x).length; // 6 mức màu h0..h5
        const head = `<tr><th>Thực tế ↓<br>Dự đoán →</th>${labels.map((l) => `<th>${seg(l)}</th>`).join("")}<th class="cm-total">Tổng</th><th>Recall</th></tr>`;
        const body = matrix.map((row, i) => {
            const total = row.reduce((s, n) => s + n, 0);
            const cells = row.map((n, j) => {
                const t = total ? n / total : 0;
                return `<td class="h${level(t)} ${i === j ? "diag" : ""}" title="${esc(`${labels[i]} → ${labels[j]}: ${n} SP (${ratio(t)})`)}"><b>${BP.formatNumber(n)}</b><small>${ratio(t)}</small></td>`;
            }).join("");
            return `<tr><th scope="row">${seg(labels[i])}</th>${cells}<td class="total cm-total"><b>${BP.formatNumber(total)}</b></td><td class="total"><b>${ratio(total ? row[i] / total : null)}</b></td></tr>`;
        }).join("");
        $("confusion").innerHTML = `<table class="cm"><thead>${head}</thead><tbody>${body}</tbody></table>`;
    }

    // ---------------------------------------------------------------- phần 3: bảng dự đoán

    function filterRows() {
        const q = BP.normalizeText($("searchInput").value);
        const group = $("groupFilter").value, result = $("resultFilter").value;
        state.filtered = state.rows.filter((r) => (!group || r.actual_price_group === group)
            && (!result || (result === "right") === isRight(r))
            && (!q || r._search.includes(q))).sort(SORTS[$("sortSelect").value]);
        state.page = 1;
        renderTable();
    }

    function rowHtml(r) {
        const right = isRight(r);
        const pctErr = r.absolute_percentage_error;
        return `<tr>
            <td class="name-cell">${esc(r.product_name)}<small>${esc(r.brand || "—")}</small></td>
            <td class="nowrap">${esc(r.primary_category || "Chưa phân loại")}</td>
            <td class="num">${BP.formatVnd(r.current_price_vnd)}</td>
            <td class="num">${BP.formatVnd(r.predicted_price_vnd)}</td>
            <td class="num nowrap">${BP.formatVnd(r.absolute_error_vnd)}<span class="err-pct ${pctErr > 50 ? "err-high" : ""}">${BP.formatPercent(pctErr)}</span></td>
            <td>${seg(r.actual_price_group)}</td>
            <td><span class="badge ${right ? "badge-good" : "badge-bad"}" title="${right ? "Phân loại đúng" : "Phân loại sai"}">${BP.icon(right ? "check" : "x")}${esc(r.classified_price_group || "—")}</span></td>
        </tr>`;
    }

    function renderTable() {
        const list = state.filtered;
        const pages = Math.max(1, Math.ceil(list.length / PAGE_SIZE));
        state.page = Math.min(Math.max(1, state.page), pages);
        const start = (state.page - 1) * PAGE_SIZE;
        const slice = list.slice(start, start + PAGE_SIZE);
        $("predBody").innerHTML = slice.length ? slice.map(rowHtml).join("")
            : `<tr><td colspan="7">${BP.stateHtml("Không có sản phẩm phù hợp bộ lọc.")}</td></tr>`;
        const wrong = list.filter((r) => !isRight(r)).length;
        $("tableInfo").textContent = list.length
            ? `Hiển thị ${BP.formatNumber(start + 1)}–${BP.formatNumber(start + slice.length)} / ${BP.formatNumber(list.length)} sản phẩm · ${BP.formatNumber(wrong)} phân loại sai`
            : "0 sản phẩm";
        BP.renderPagination($("pagination"), state.page, pages, (p) => {
            state.page = p;
            renderTable();
            $("tableCard").scrollIntoView({ behavior: "smooth", block: "start" });
        });
    }

    function exportCsv() {
        const rows = [["Mã SP", "Tên sản phẩm", "Thương hiệu", "Danh mục", "Giá thực tế (VND)", "Giá dự đoán (VND)", "Sai số (VND)", "Sai số (%)",
            "Nhóm thực tế", "Nhóm theo giá dự đoán (hồi quy)", "Nhóm do mô hình phân loại", "Phân loại đúng"]];
        state.filtered.forEach((r) => rows.push([r.product_id, r.product_name, r.brand, r.primary_category || "", Math.round(r.current_price_vnd),
            Math.round(r.predicted_price_vnd), Math.round(r.absolute_error_vnd), r.absolute_percentage_error.toFixed(2),
            r.actual_price_group, r.predicted_price_group || "", r.classified_price_group, isRight(r) ? "Đúng" : "Sai"]));
        BP.downloadCsv(`du-doan-gia-tap-test-${new Date().toISOString().slice(0, 10)}.csv`, rows);
        BP.toast(`Đã xuất ${BP.formatNumber(state.filtered.length)} dòng ra CSV.`);
    }

    // ---------------------------------------------------------------- nhận định

    function renderInsights(d) {
        const m = d.metrics || {}, c = d.classification;
        const items = [];
        const dummy = (d.model_comparison || []).find((r) => r.model_name.startsWith("Dummy"))?.metrics?.validation;
        const chosen = (d.model_comparison || []).find((r) => r.is_selected)?.metrics?.validation;
        items.push(`Mô hình <b>${esc(m.model || "—")}</b> đạt R² = <b>${BP.formatNumber(m.r2, "—", 3)}</b> trên tập test: giá dự đoán lệch trung bình <b>${BP.formatVnd(m.mae)}</b> (MAPE ${BP.formatPercent(m.mape)}).`
            + (dummy && chosen ? ` So với mốc Dummy (luôn đoán giá trung vị), MAE validation giảm <b>${BP.formatPercent((1 - chosen.mae / dummy.mae) * 100, 0)}</b>.` : ""));

        const n = state.rows.length;
        const within = state.rows.filter((r) => r.absolute_percentage_error <= 20).length;
        const over = state.rows.filter((r) => r.absolute_percentage_error > 50).length;
        if (n) items.push(`<b>${ratio(within / n, 0)}</b> sản phẩm có giá dự đoán nằm trong khoảng ±20% giá thật, còn <b>${ratio(over / n, 0)}</b> lệch hơn 50% — xem các dòng đầu bảng (sắp theo sai số %) để thấy những trường hợp khó.`);

        const fi = d.feature_importance?.regression || [];
        if (fi.length >= 3) {
            const top3 = fi.slice(0, 3);
            items.push(`Ba đặc trưng quan trọng nhất là <b>${top3.map((f) => esc(FEATURE_LABELS[f.feature] || f.feature)).join(", ")}</b> (cộng lại ${ratio(top3.reduce((s, f) => s + f.importance, 0), 0)}), trong khi rating và số lượt đánh giá chỉ đóng góp `
                + `${ratio(fi.filter((f) => ["rating", "review_count_log"].includes(f.feature)).reduce((s, f) => s + f.importance, 0))}: giá do sản phẩm “là gì” quyết định nhiều hơn mức độ được yêu thích.`);
        }

        const groups = groupStats();
        if (groups.length) {
            const best = groups.reduce((a, b) => (b.mape < a.mape ? b : a));
            const worst = groups.reduce((a, b) => (b.mape > a.mape ? b : a));
            items.push(`Theo nhóm giá, nhóm <b>${esc(best.label)}</b> được dự đoán chính xác nhất (MAPE ${BP.formatPercent(best.mape)}), nhóm <b>${esc(worst.label)}</b> kém nhất (${BP.formatPercent(worst.mape)})`
                + (worst.label === "Thấp" ? " — cùng một mức lệch VND chiếm tỷ lệ lớn hơn trên giá nhỏ." : "."));
        }

        if (c?.confusion_matrix?.matrix) {
            const { labels, matrix } = c.confusion_matrix;
            let worst = null;
            matrix.forEach((row, i) => row.forEach((n, j) => { if (i !== j && (!worst || n > worst.n)) worst = { n, from: labels[i], to: labels[j] }; }));
            const recalls = matrix.map((row, i) => ({ label: labels[i], r: row[i] / (row.reduce((s, v) => s + v, 0) || 1) }));
            const hardest = recalls.reduce((a, b) => (b.r < a.r ? b : a));
            items.push(`Mô hình phân loại <b>${esc(c.model)}</b> đoán đúng <b>${ratio(c.accuracy)}</b> phân khúc (F1-macro ${BP.formatNumber(c.f1_macro, "—", 3)}).`
                + (worst ? ` Nhầm lẫn nhiều nhất: <b>${esc(worst.from)} → ${esc(worst.to)}</b> (${BP.formatNumber(worst.n)} SP); nhóm khó nhận ra nhất là <b>${esc(hardest.label)}</b> (recall ${ratio(hardest.r)})`
                    + (hardest.label === "Trung bình" ? " vì nằm kẹp giữa hai ngưỡng." : ".") : ""));
        }
        $("insights").innerHTML = items.map((html, i) => `<li><span class="ins-no">${i + 1}</span><span>${html}</span></li>`).join("");
    }

    // ---------------------------------------------------------------- khởi động

    function showError(message) {
        const box = $("pageError");
        box.innerHTML = BP.icon("alert") + `<div>${esc(message)}</div>`;
        box.hidden = false;
        document.querySelectorAll(".chart-box").forEach((el) => { el.classList.remove("is-loading"); el.innerHTML = BP.stateHtml(message, "error"); });
        $("confusion").innerHTML = BP.stateHtml(message, "error");
        $("predBody").innerHTML = `<tr><td colspan="7">${BP.stateHtml(message, "error")}</td></tr>`;
        $("insights").innerHTML = "";
        ["regModel", "clfModel", "tableInfo"].forEach((id) => { $(id).textContent = "Không có dữ liệu."; });
    }

    async function init() {
        document.querySelectorAll("[data-icon]").forEach((el) => {
            if (el.tagName === "SPAN") el.outerHTML = BP.icon(el.dataset.icon); else el.innerHTML = BP.icon(el.dataset.icon);
        });
        $("predBody").innerHTML = `<tr><td colspan="7">${BP.stateHtml("Đang tải kết quả dự đoán...", "loading")}</td></tr>`;
        try {
            const d = await BP.api("/api/predictions");
            state.data = d;
            state.rows = (d.predictions || []).map((r) => ({ ...r, _search: BP.normalizeText(`${r.product_name} ${r.brand} ${r.primary_category || ""}`) }));
            renderRegression(d);
            renderClassification(d);
            renderInsights(d);
            filterRows();
            $("exportBtn").disabled = false;
        } catch (err) {
            showError(err.message);
            return;
        }
        $("featureTask").addEventListener("change", drawFeatures);
        $("searchInput").addEventListener("input", BP.debounce(filterRows, 200));
        ["groupFilter", "resultFilter", "sortSelect"].forEach((id) => $(id).addEventListener("change", filterRows));
        $("exportBtn").addEventListener("click", exportCsv);
    }

    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
