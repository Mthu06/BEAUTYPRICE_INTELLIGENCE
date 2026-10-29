/* saoluu.js - sao lưu & phục hồi CSDL (chỉ quản trị viên) */
(function () {
    "use strict";

    const $ = (id) => document.getElementById(id);
    const TABLE_LABELS = {
        retailers: "Nhà bán lẻ", categories: "Danh mục", products: "Sản phẩm", product_categories: "Sản phẩm – danh mục",
        price_snapshots: "Snapshot giá", reviews: "Đánh giá", users: "Người dùng", collection_logs: "Nhật ký thu thập",
        etl_log: "Nhật ký làm sạch", ml_runs: "Lần huấn luyện", ml_price_predictions: "Dự đoán giá",
        ml_clusters: "Phân cụm", ml_anomalies: "Bất thường"
    };
    let pendingRestore = null;
    let busy = false;

    const formatSize = (bytes) => BP.toNumber(bytes) === null ? "—" : BP.formatNumber(bytes / 1048576, "—", 1) + " MB";
    const integrityBadge = (info) => info?.integrity === "ok" && !info.foreign_key_errors
        ? `<span class="badge badge-good">${BP.icon("check")}Toàn vẹn</span>`
        : `<span class="badge badge-bad">${BP.icon("alert")}${BP.escapeHtml(info?.integrity || "Chưa kiểm tra")}</span>`;

    function notice(message, type = "info") {
        $("pageNotice").innerHTML = message
            ? `<div class="notice notice-${type}">${BP.icon(type === "bad" ? "alert" : "info")}<span>${BP.escapeHtml(message)}</span></div>` : "";
    }

    function renderCurrent(current, backups) {
        $("kpiSize").textContent = formatSize(current.size_bytes);
        $("kpiPath").textContent = current.path;
        $("kpiIntegrity").textContent = current.integrity === "ok" ? "OK" : current.integrity;
        $("kpiFk").textContent = `${BP.formatNumber(current.foreign_key_errors)} lỗi khóa ngoại`;
        $("kpiRows").textContent = `${BP.formatNumber(current.counts.products)} / ${BP.formatNumber(current.counts.price_snapshots)}`;
        $("kpiRowsSub").textContent = `${BP.formatNumber(current.counts.reviews)} đánh giá · ${BP.formatNumber(current.counts.users)} người dùng`;
        $("kpiBackups").textContent = BP.formatNumber(backups.length);
        $("kpiLast").textContent = backups.length ? `Gần nhất: ${BP.formatDate(backups[0].created_at, true)}` : "Chưa có bản sao lưu";
    }

    function renderBackups(backups) {
        $("backupTable").innerHTML = backups.length ? backups.map((b) => `
            <tr>
                <td class="name-cell">${BP.escapeHtml(b.name)}${b.source === "upload" ? ' <span class="badge badge-info">Tải lên</span>' : ""}<small>${BP.escapeHtml(b.note || "")}</small></td>
                <td class="nowrap">${BP.formatDate(b.created_at, true)}</td>
                <td>${BP.escapeHtml(b.created_by || "—")}</td>
                <td class="num">${formatSize(b.size_bytes)}</td>
                <td class="num nowrap">${BP.formatNumber(b.counts?.products)} / ${BP.formatNumber(b.counts?.price_snapshots)}</td>
                <td>${integrityBadge(b)}</td>
                <td><div class="row">
                    <button type="button" class="btn btn-outline btn-sm" data-download="${BP.escapeHtml(b.name)}">${BP.icon("download")}Tải về</button>
                    <button type="button" class="btn btn-outline btn-sm" data-restore="${BP.escapeHtml(b.name)}">${BP.icon("refresh")}Phục hồi</button>
                </div></td>
            </tr>`).join("")
            : `<tr><td colspan="7">${BP.stateHtml("Chưa có bản sao lưu nào. Bấm “Tạo bản sao lưu” để bắt đầu.")}</td></tr>`;
    }

    async function load() {
        $("backupTable").innerHTML = `<tr><td colspan="7">${BP.stateHtml("Đang tải...", "loading")}</td></tr>`;
        try {
            const data = await BP.api("/api/backups");
            $("backupDir").textContent = `Thư mục: ${data.backup_dir}`;
            renderCurrent(data.current, data.backups);
            renderBackups(data.backups);
        } catch (err) {
            notice(err.message, "bad");
            $("backupTable").innerHTML = `<tr><td colspan="7">${BP.stateHtml(err.message, "error")}</td></tr>`;
        }
    }

    async function setBusy(button, label, task) {
        if (busy) return;
        busy = true;
        const old = button.innerHTML;
        button.disabled = true;
        button.textContent = label;
        try { await task(); } finally { busy = false; button.disabled = false; button.innerHTML = old; }
    }

    function makeBackup() {
        return setBusy($("backupBtn"), "Đang sao lưu...", async () => {
            try {
                const data = await BP.api("/api/backups", { method: "POST", body: { note: "Sao lưu thủ công từ website" } });
                BP.toast(data.message);
                await load();
            } catch (err) { BP.toast(err.message, "bad"); }
        });
    }

    async function download(name) {
        // Cần gửi token nên tải bằng fetch rồi tạo link tạm.
        try {
            const response = await fetch(`${BP.API_BASE}/api/backups/${encodeURIComponent(name)}/download`,
                { headers: { Authorization: `Bearer ${BP.getSession().token}` } });
            if (!response.ok) throw new Error((await response.json().catch(() => ({}))).message || `HTTP ${response.status}`);
            const link = Object.assign(document.createElement("a"), { href: URL.createObjectURL(await response.blob()), download: name });
            document.body.appendChild(link);
            link.click();
            setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 0);
        } catch (err) { BP.toast(`Không tải được: ${err.message}`, "bad"); }
    }

    function upload(file) {
        if (!file) return;
        if (!/\.(db|sqlite3?)$/i.test(file.name)) return BP.toast("Chỉ nhận tệp .db / .sqlite / .sqlite3.", "bad");
        return setBusy($("uploadBtn"), "Đang tải lên...", async () => {
            $("dropZone").classList.add("is-busy");
            try {
                const form = new FormData();
                form.append("file", file);
                // Gửi multipart nên không dùng BP.api (luôn gửi JSON).
                const response = await fetch(`${BP.API_BASE}/api/backups/upload`,
                    { method: "POST", headers: { Authorization: `Bearer ${BP.getSession().token}` }, body: form });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
                BP.toast(data.message);
                await load();
                busy = false;
                openConfirm(data.backup.name, `Tệp “${file.name}” hợp lệ: ${BP.formatNumber(data.backup.counts.products)} sản phẩm, `
                    + `${BP.formatNumber(data.backup.counts.price_snapshots)} snapshot giá. Phục hồi ngay?`);
            } catch (err) {
                BP.toast(`Không tải lên được: ${err.message}`, "bad");
            } finally {
                $("dropZone").classList.remove("is-busy");
                $("uploadInput").value = "";
            }
        });
    }

    function openConfirm(name, intro = "") {
        pendingRestore = name;
        $("confirmName").textContent = name;
        $("confirmWarn").innerHTML = `${BP.icon("alert")}<span>${BP.escapeHtml(intro)} Dữ liệu hiện tại sẽ được thay bằng bản sao lưu <b>${BP.escapeHtml(name)}</b>.</span>`;
        $("confirmModal").hidden = false;
    }

    function closeConfirm() {
        if (busy) return;
        $("confirmModal").hidden = true;
        pendingRestore = null;
    }

    function renderResult(data) {
        const v = data.verification;
        $("resultCard").hidden = false;
        $("resultSub").textContent = `Phục hồi từ ${data.restored_from}. Bản an toàn tạo trước khi phục hồi: ${data.safety_backup}. `
            + `Toàn vẹn: ${v.integrity}, lỗi khóa ngoại: ${v.foreign_key_errors}.`;
        $("resultBadge").innerHTML = data.verified
            ? `<span class="badge badge-good">${BP.icon("check")}Đã kiểm tra: khớp 100%</span>`
            : `<span class="badge badge-bad">${BP.icon("alert")}Không khớp</span>`;
        $("resultTable").innerHTML = Object.keys(v.counts_backup).map((t) => {
            const same = v.counts_backup[t] === v.counts_after_restore[t];
            return `<tr><td>${BP.escapeHtml(TABLE_LABELS[t] || t)} <small class="muted">${BP.escapeHtml(t)}</small></td>
                <td class="num">${BP.formatNumber(v.counts_backup[t])}</td><td class="num">${BP.formatNumber(v.counts_after_restore[t])}</td>
                <td>${same ? `<span class="badge badge-good">${BP.icon("check")}Khớp</span>` : `<span class="badge badge-bad">${BP.icon("x")}Lệch</span>`}</td></tr>`;
        }).join("");
        $("resultCard").scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function restore() {
        const name = pendingRestore;
        return setBusy($("confirmRestore"), "Đang phục hồi...", async () => {
            try {
                const data = await BP.api(`/api/backups/${encodeURIComponent(name)}/restore`, { method: "POST" });
                BP.toast(data.message, data.verified ? "good" : "bad");
                BP.notifyProductsUpdated();
                busy = false;
                closeConfirm();
                renderResult(data);
                await load();
            } catch (err) { BP.toast(err.message, "bad"); }
        });
    }

    document.addEventListener("DOMContentLoaded", () => {
        $("reloadBtn").innerHTML = `${BP.icon("refresh")}Tải lại`;
        $("backupBtn").innerHTML = `${BP.icon("database")}Tạo bản sao lưu`;
        $("uploadBtn").innerHTML = `${BP.icon("upload")}Tải lên bản sao lưu`;
        $("dropIcon").innerHTML = BP.icon("upload");
        [["icDb", "database"], ["icIntegrity", "check"], ["icBox", "box"], ["icCount", "layers"]].forEach(([id, name]) => { $(id).innerHTML = BP.icon(name); });

        if (!BP.isAdmin()) {
            notice("Chức năng sao lưu & phục hồi chỉ dành cho quản trị viên.", "warn");
            $("backupBtn").disabled = true;
            $("uploadBtn").disabled = true;
            $("dropZone").hidden = true;
            $("backupTable").innerHTML = `<tr><td colspan="7">${BP.stateHtml("Bạn không có quyền xem trang này.", "error")}</td></tr>`;
            return;
        }
        $("reloadBtn").addEventListener("click", load);
        $("backupBtn").addEventListener("click", makeBackup);
        const pick = () => { if (!busy) $("uploadInput").click(); };
        $("uploadBtn").addEventListener("click", pick);
        $("uploadInput").addEventListener("change", (event) => upload(event.target.files[0]));
        const drop = $("dropZone");
        drop.addEventListener("click", pick);
        drop.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); pick(); } });
        drop.addEventListener("dragover", (event) => { event.preventDefault(); drop.classList.add("is-over"); });
        drop.addEventListener("dragleave", () => drop.classList.remove("is-over"));
        drop.addEventListener("drop", (event) => { event.preventDefault(); drop.classList.remove("is-over"); upload(event.dataTransfer.files[0]); });
        $("backupTable").addEventListener("click", (event) => {
            const btn = event.target.closest("button");
            if (btn?.dataset.download) download(btn.dataset.download);
            if (btn?.dataset.restore) openConfirm(btn.dataset.restore);
        });
        $("cancelRestore").addEventListener("click", closeConfirm);
        $("confirmRestore").addEventListener("click", restore);
        $("confirmModal").addEventListener("click", (event) => { if (event.target === event.currentTarget) closeConfirm(); });
        document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeConfirm(); });
        load();
    });
})();
