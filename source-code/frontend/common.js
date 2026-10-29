/* common.js - dùng chung cho mọi trang BeautyPrice.
 * Nạp trong <head> TRƯỚC script của trang: kiểm tra đăng nhập ngay, không để trang hiện ra rồi mới chuyển hướng.
 *
 * Trang chỉ cần:  <body><div class="app"><aside class="sidebar" id="sidebar"></aside><main class="main">...</main></div>
 * common.js tự dựng thanh điều hướng, khối người dùng, nút đăng xuất và nút menu trên màn hình hẹp.
 *
 * API_BASE:
 *  - Mở qua Flask (http://127.0.0.1:5000/...) -> cùng origin, gọi "/api/...".
 *  - Mở bằng Live Server (:5500) hoặc file:// -> gọi http://<host>:5000.
 *  - Có thể ghi đè bằng window.BEAUTY_API_BASE trước khi nạp file này.
 */
(function () {
    "use strict";

    const KEYS = { token: "beautyprice_token", role: "beautyprice_role", user: "beautyprice_username" };
    const LOGIN_PAGE = "login.html";
    const HOME_PAGE = "dashboard.html";
    const PRODUCTS_UPDATED_KEY = "beautyprice_products_updated";

    const servedByFlask = location.protocol.startsWith("http") && location.port !== "5500";
    const API_BASE = window.BEAUTY_API_BASE ?? (servedByFlask ? "" : `http://${location.hostname || "127.0.0.1"}:5000`);
    const isLoginPage = /(^|\/)login\.html$/i.test(location.pathname);

    const store = {
        get: (key) => { try { return sessionStorage.getItem(key); } catch { return null; } },
        set: (key, value) => { try { sessionStorage.setItem(key, value); } catch { /* chế độ riêng tư */ } },
        remove: (key) => { try { sessionStorage.removeItem(key); } catch { /* bỏ qua */ } }
    };

    function getSession() {
        const token = store.get(KEYS.token);
        return token ? { token, role: (store.get(KEYS.role) || "user").toLowerCase(), username: store.get(KEYS.user) || "" } : null;
    }

    function saveSession(token, user) {
        store.set(KEYS.token, token);
        store.set(KEYS.role, String(user?.role || "user").toLowerCase());
        store.set(KEYS.user, user?.username || "");
    }

    function clearSession() {
        Object.values(KEYS).forEach(store.remove);
    }

    function goLogin() {
        clearSession();
        location.replace(LOGIN_PAGE);
    }

    async function api(path, { method = "GET", body, auth = true } = {}) {
        const headers = {};
        if (body !== undefined) headers["Content-Type"] = "application/json";
        const session = getSession();
        if (auth && session) headers.Authorization = `Bearer ${session.token}`;

        let response;
        try {
            response = await fetch(API_BASE + path, {
                method, headers, cache: "no-store",
                body: body === undefined ? undefined : JSON.stringify(body)
            });
        } catch {
            throw new Error(`Không kết nối được backend (${API_BASE || location.origin}). Hãy chạy run.bat / run.sh rồi tải lại trang.`);
        }

        const data = await response.json().catch(() => ({}));
        if (response.status === 401 && auth && !isLoginPage) {
            goLogin();
            throw new Error(data.message || "Phiên đăng nhập đã hết hạn.");
        }
        if (!response.ok || data.status === "error" || data.success === false) {
            const error = new Error(data.message || `Lỗi máy chủ (HTTP ${response.status}).`);
            error.status = response.status;
            throw error;
        }
        return data;
    }

    async function logout() {
        try { await api("/api/logout", { method: "POST" }); } catch { /* vẫn đăng xuất phía client */ }
        goLogin();
    }

    // ---------------------------------------------------------------- biểu tượng (SVG nét, 24x24)

    const ICONS = {
        dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
        search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
        clusters: '<circle cx="7" cy="7" r="3"/><circle cx="17" cy="8" r="3"/><circle cx="11" cy="17" r="3"/>',
        predict: '<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
        anomaly: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
        report: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h6"/>',
        logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
        menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
        plus: '<path d="M12 5v14M5 12h14"/>',
        edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
        trash: '<path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
        eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
        download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
        printer: '<path d="M6 9V2h12v7"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
        x: '<path d="M18 6 6 18M6 6l12 12"/>',
        check: '<path d="M20 6 9 17l-5-5"/>',
        info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
        alert: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>',
        box: '<path d="M21 16V8a2 2 0 0 0-1-1.7l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.7l7 4a2 2 0 0 0 2 0l7-4a2 2 0 0 0 1-1.7z"/><path d="M3.3 7 12 12l8.7-5M12 22V12"/>',
        tag: '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><path d="M7 7h.01"/>',
        percent: '<path d="M19 5 5 19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
        star: '<path d="m12 2 3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"/>',
        store: '<path d="M3 9l1.5-5h15L21 9"/><path d="M4 9v11h16V9"/><path d="M9 20v-6h6v6"/><path d="M3 9a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0"/>',
        refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
        database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/>',
        external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6M10 14 21 3"/>',
        chevronLeft: '<path d="m15 18-6-6 6-6"/>',
        chevronRight: '<path d="m9 18 6-6-6-6"/>',
        target: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>',
        layers: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5M2 12l10 5 10-5"/>'
    };
    const icon = (name, cls = "") =>
        `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;

    // ---------------------------------------------------------------- khung trang

    const NAV = [
        { href: "dashboard.html", label: "Tổng quan", icon: "dashboard" },
        { href: "tracuu.html", label: "Tra cứu dữ liệu", icon: "search" },
        { group: "Phân tích & mô hình" },
        { href: "phankhuc.html", label: "Phân khúc (K-Means)", icon: "clusters" },
        { href: "dudoan.html", label: "Dự đoán giá", icon: "predict" },
        { href: "batthuong.html", label: "Phát hiện bất thường", icon: "anomaly" },
        { group: "Báo cáo" },
        { href: "baocao.html", label: "Báo cáo thống kê", icon: "report" },
        { group: "Quản trị", admin: true },
        { href: "saoluu.html", label: "Sao lưu & phục hồi", icon: "database", admin: true }
    ];

    function renderShell(session) {
        const sidebar = document.getElementById("sidebar");
        if (!sidebar) return;
        const current = (location.pathname.split("/").pop() || HOME_PAGE).toLowerCase();
        const isAdmin = session.role === "admin";
        sidebar.innerHTML = `
            <a class="brand" href="${HOME_PAGE}">
                <span class="brand-mark">B</span>
                <span><span class="brand-name">BeautyPrice</span><br><span class="brand-sub">Intelligence</span></span>
            </a>
            <nav class="nav">${NAV.filter((item) => isAdmin || !item.admin).map((item) => item.group
                ? `<div class="nav-label">${escapeHtml(item.group)}</div>`
                : `<a href="${item.href}" class="${item.href === current ? "active" : ""}">${icon(item.icon)}<span>${escapeHtml(item.label)}</span></a>`).join("")}
            </nav>
            <div class="side-user">
                <span class="avatar" id="userAvatar">${escapeHtml((session.username || "?").charAt(0).toUpperCase())}</span>
                <span class="side-user-info">
                    <span class="side-user-name" id="userName">${escapeHtml(session.username || "")}</span><br>
                    <span class="side-user-role" id="userRole">${isAdmin ? "Quản trị viên" : "Người dùng"}</span>
                </span>
                <button type="button" class="icon-btn logout-btn" title="Đăng xuất" aria-label="Đăng xuất">${icon("logout")}</button>
            </div>`;
        sidebar.querySelector(".logout-btn").addEventListener("click", logout);

        const head = document.querySelector(".page-head");
        if (head && !head.querySelector(".menu-toggle")) {
            const toggle = document.createElement("button");
            toggle.type = "button";
            toggle.className = "btn btn-outline btn-icon menu-toggle";
            toggle.setAttribute("aria-label", "Mở menu");
            toggle.innerHTML = icon("menu");
            toggle.addEventListener("click", () => document.body.classList.toggle("nav-open"));
            head.prepend(toggle);
        }
        document.addEventListener("click", (event) => {
            if (document.body.classList.contains("nav-open") && !sidebar.contains(event.target) && !event.target.closest(".menu-toggle")) {
                document.body.classList.remove("nav-open");
            }
        });
    }

    // ---------------------------------------------------------------- định dạng & tiện ích

    const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) =>
        ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[ch]));

    function safeUrl(value) {
        try {
            const url = new URL(String(value || ""));
            return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
        } catch {
            return "";
        }
    }

    /** Số hữu hạn hoặc null (không biến dữ liệu thiếu thành 0). */
    function toNumber(value) {
        if (value === null || value === undefined || typeof value === "boolean") return null;
        if (typeof value === "number") return Number.isFinite(value) ? value : null;
        const s = String(value).trim();
        if (!/\d/.test(s)) return null;
        const direct = Number(s);
        if (Number.isFinite(direct)) return direct;
        const number = Number(s.replace(/[^\d.-]/g, "")); // "549.000đ", "20%"
        return Number.isFinite(number) ? number : null;
    }

    const formatters = {};
    const fmt = (digits) => (formatters[digits] ??= new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits }));
    const formatNumber = (value, fallback = "—", digits = 0) => {
        const number = toNumber(value);
        return number === null ? fallback : fmt(digits).format(number);
    };
    const formatVnd = (value, fallback = "—") => {
        const number = toNumber(value);
        return number === null ? fallback : fmt(0).format(Math.round(number)) + "đ";
    };
    /** 1.234.000đ -> "1,2 tr", 340.000 -> "340k" (nhãn trục biểu đồ). */
    const formatVndShort = (value) => {
        const n = toNumber(value);
        if (n === null) return "—";
        if (Math.abs(n) >= 1e6) return fmt(1).format(n / 1e6) + " tr";
        if (Math.abs(n) >= 1e3) return fmt(0).format(n / 1e3) + "k";
        return fmt(0).format(n);
    };
    const formatPercent = (value, digits = 1, fallback = "—") => {
        const number = toNumber(value);
        return number === null ? fallback : fmt(digits).format(number) + "%";
    };
    const formatRating = (value, fallback = "—") => {
        const number = toNumber(value);
        return number === null || number <= 0 ? fallback : fmt(1).format(number);
    };
    function formatDate(value, withTime = false) {
        if (!value) return "—";
        const date = new Date(String(value).replace(" ", "T"));
        if (Number.isNaN(date.getTime())) return String(value);
        return date.toLocaleString("vi-VN", withTime
            ? { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }
            : { day: "2-digit", month: "2-digit", year: "numeric" });
    }

    /** Bỏ dấu tiếng Việt, ký tự vô hình, viết thường - dùng cho tìm kiếm. */
    const normalizeText = (value) => String(value ?? "").toLowerCase().normalize("NFD")
        .replace(/[\u0300-\u036f\u200b-\u200d\ufeff]/g, "").replace(/đ/g, "d").replace(/\s+/g, " ").trim();

    /** Ngày review: ISO từ CSDL, Hasaki "2025-09-27 17:17:59", Guardian "22 tháng 4, 2025". Trả về timestamp hoặc 0. */
    function parseReviewDate(value) {
        const s = String(value || "").trim();
        let m = s.match(/^(\d{1,2})\s*tháng\s*(\d{1,2}),?\s*(\d{4})/i);
        if (m) return new Date(+m[3], +m[2] - 1, +m[1]).getTime();
        m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?/);
        if (m) return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0)).getTime();
        const t = Date.parse(s);
        return Number.isFinite(t) ? t : 0;
    }

    /** Khoảng giá thống nhất (nửa mở [min, max)). */
    const PRICE_BANDS = [
        { key: "under100", label: "Dưới 100K", min: 0, max: 100000 },
        { key: "100to300", label: "100K – 300K", min: 100000, max: 300000 },
        { key: "300to500", label: "300K – 500K", min: 300000, max: 500000 },
        { key: "500to1m", label: "500K – 1 triệu", min: 500000, max: 1000000 },
        { key: "over1m", label: "Từ 1 triệu", min: 1000000, max: Infinity }
    ];
    const priceBand = (value) => {
        const price = toNumber(value);
        return price === null || price <= 0 ? null : PRICE_BANDS.find((b) => price >= b.min && price < b.max)?.key ?? null;
    };

    /** Nhóm giảm giá thống nhất: "0" (không giảm / không có giá niêm yết) | (0,10] | (10,20] | (20,30] | >30. */
    const DISCOUNT_BANDS = { "0": "Không giảm", "1to10": "≤ 10%", "11to20": "10 – 20%", "21to30": "20 – 30%", "over30": "> 30%" };
    function discountBucket(value) {
        const d = toNumber(value) ?? 0;
        if (d <= 0) return "0";
        if (d <= 10) return "1to10";
        if (d <= 20) return "11to20";
        if (d <= 30) return "21to30";
        return "over30";
    }

    function median(values) {
        const sorted = values.map(toNumber).filter((v) => v !== null).sort((a, b) => a - b);
        if (!sorted.length) return null;
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    }

    const average = (values) => {
        const valid = values.map(toNumber).filter((v) => v !== null);
        return valid.length ? valid.reduce((sum, v) => sum + v, 0) / valid.length : null;
    };

    /** Giá trị xuất hiện nhiều nhất: [giá trị, số lần] hoặc null. */
    function mostCommon(values) {
        const counts = new Map();
        for (const v of values) if (v !== null && v !== undefined && v !== "") counts.set(v, (counts.get(v) || 0) + 1);
        let best = null;
        for (const entry of counts) if (!best || entry[1] > best[1]) best = entry;
        return best;
    }

    function debounce(fn, wait = 250) {
        let timer;
        return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), wait); };
    }

    /** Gom review theo review_key (backend tạo sẵn cho cả sản phẩm và review). */
    function groupReviews(reviews) {
        const map = new Map();
        for (const review of reviews || []) {
            if (!review.review_key) continue;
            if (!map.has(review.review_key)) map.set(review.review_key, []);
            map.get(review.review_key).push(review);
        }
        return map;
    }

    /** Báo các tab khác rằng danh sách sản phẩm đã đổi / lắng nghe tín hiệu đó. */
    function notifyProductsUpdated() {
        try { localStorage.setItem(PRODUCTS_UPDATED_KEY, String(Date.now())); } catch { /* bỏ qua */ }
    }
    function onProductsUpdated(callback) {
        window.addEventListener("storage", (event) => { if (event.key === PRODUCTS_UPDATED_KEY) callback(); });
    }

    // ---------------------------------------------------------------- thành phần giao diện

    /** Phân trang có dấu "…". onChange(page) được gọi khi bấm. */
    function renderPagination(container, page, totalPages, onChange) {
        if (!container) return;
        if (totalPages <= 1) { container.innerHTML = ""; return; }
        const pages = [];
        for (let p = 1; p <= totalPages; p++) {
            if (p === 1 || p === totalPages || Math.abs(p - page) <= 1) pages.push(p);
            else if (pages[pages.length - 1] !== "…") pages.push("…");
        }
        container.innerHTML =
            `<button type="button" class="page-btn" data-page="${page - 1}" ${page <= 1 ? "disabled" : ""} aria-label="Trang trước">‹</button>` +
            pages.map((p) => p === "…" ? '<span class="page-gap">…</span>'
                : `<button type="button" class="page-btn ${p === page ? "active" : ""}" data-page="${p}">${p}</button>`).join("") +
            `<button type="button" class="page-btn" data-page="${page + 1}" ${page >= totalPages ? "disabled" : ""} aria-label="Trang sau">›</button>`;
        container.onclick = (event) => {
            const btn = event.target.closest(".page-btn");
            if (btn && !btn.disabled) onChange(Number(btn.dataset.page));
        };
    }

    function toast(message, type = "good") {
        let stack = document.querySelector(".toast-stack");
        if (!stack) {
            stack = document.createElement("div");
            stack.className = "toast-stack";
            stack.setAttribute("role", "status");
            document.body.appendChild(stack);
        }
        const item = document.createElement("div");
        item.className = `toast ${type}`;
        item.innerHTML = icon(type === "bad" ? "alert" : "check") + `<span>${escapeHtml(message)}</span>`;
        stack.appendChild(item);
        setTimeout(() => item.remove(), 3500);
    }

    /** Ô trạng thái (đang tải / trống / lỗi) để đặt vào card hoặc tbody. */
    const stateHtml = (message, type = "empty") =>
        `<div class="state ${type === "error" ? "error" : ""}">${icon(type === "error" ? "alert" : type === "loading" ? "refresh" : "info")}<div>${escapeHtml(message)}</div></div>`;

    /** Xuất CSV (UTF-8 có BOM cho Excel, chống chèn công thức). rows: mảng các mảng. */
    function downloadCsv(filename, rows) {
        const cell = (value) => {
            let text = String(value ?? "");
            if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
            return /[",\n\r;]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
        };
        const blob = new Blob(["\ufeff" + rows.map((r) => r.map(cell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" });
        const link = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: filename });
        document.body.appendChild(link);
        link.click();
        setTimeout(() => { URL.revokeObjectURL(link.href); link.remove(); }, 0);
    }

    // ---------------------------------------------------------------- biểu đồ (Chart.js nạp cục bộ từ vendor/)

    /** Bảng màu đã kiểm định mù màu (thứ tự cố định, không xoay vòng). Màu đi theo thực thể, không theo thứ hạng. */
    const COLORS = {
        series: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
        retailer: { cocolux: "#2a78d6", guardian: "#eb6834", hasaki: "#1baf7a", the_gioi_skin_food: "#eda100", watsons: "#e87ba4" },
        segment: { "Thấp": "#86b6ef", "Trung bình": "#2a78d6", "Cao": "#184f95" },
        status: { good: "#0ca30c", warn: "#fab219", serious: "#ec835a", bad: "#d03b3b" },
        ink: "#151821", ink2: "#4b5163", muted: "#8a90a2", grid: "#eceef3", axis: "#d5d8e3"
    };
    const RETAILER_NAMES = { cocolux: "Cocolux", guardian: "Guardian", hasaki: "Hasaki", the_gioi_skin_food: "The Gioi Skin Food", watsons: "Watsons" };
    const retailerKey = (value) => {
        const s = normalizeText(value).replace(/\s+/g, "_");
        return Object.keys(RETAILER_NAMES).find((k) => k === s || normalizeText(RETAILER_NAMES[k]).replace(/\s+/g, "_") === s) || s;
    };
    const retailerColor = (value) => COLORS.retailer[retailerKey(value)] || COLORS.muted;

    const charts = new WeakMap();
    let chartDefaultsApplied = false;

    function applyChartDefaults() {
        if (chartDefaultsApplied || !window.Chart) return;
        const d = window.Chart.defaults;
        d.font.family = getComputedStyle(document.body).fontFamily;
        d.font.size = 12;
        d.locale = "vi-VN"; // số trên trục/tooltip dạng 3.000 thay vì 3,000
        d.color = COLORS.ink2;
        d.borderColor = COLORS.grid;
        d.maintainAspectRatio = false;
        d.animation.duration = 350;
        d.plugins.legend.labels.usePointStyle = true;
        d.plugins.legend.labels.boxWidth = 8;
        d.plugins.legend.labels.boxHeight = 8;
        d.plugins.legend.labels.padding = 14;
        Object.assign(d.plugins.tooltip, {
            backgroundColor: "#151821", titleColor: "#fff", bodyColor: "#e6e8ef", padding: 10, cornerRadius: 8,
            boxPadding: 4, usePointStyle: true, titleFont: { weight: "600" }
        });
        d.elements.bar.borderRadius = 4;
        d.elements.bar.borderSkipped = "start";
        d.elements.line.borderWidth = 2;
        d.elements.point.radius = 3;
        d.elements.point.hoverRadius = 5;
        d.datasets.bar.maxBarThickness = 44;
        // Khi in/lưu PDF, khổ giấy khác màn hình -> vẽ lại mọi biểu đồ cho vừa.
        const resizeAll = () => Object.values(window.Chart.instances || {}).forEach((c) => { c.resize(); c.update("none"); });
        window.addEventListener("beforeprint", resizeAll);
        window.addEventListener("afterprint", resizeAll);
        chartDefaultsApplied = true;
    }

    /** Vẽ (hoặc vẽ lại) biểu đồ trên canvas. Nếu Chart.js không nạp được, hiện thông báo thay vì làm hỏng trang. */
    function chart(target, config) {
        const canvas = typeof target === "string" ? document.getElementById(target) : target;
        if (!canvas) return null;
        charts.get(canvas)?.destroy();
        if (!window.Chart) {
            canvas.parentElement.innerHTML = stateHtml("Không nạp được thư viện biểu đồ (vendor/chart.umd.min.js).", "error");
            return null;
        }
        applyChartDefaults();
        const instance = new window.Chart(canvas, config);
        charts.set(canvas, instance);
        return instance;
    }

    /** Trục giá dạng rút gọn (100k, 1,2 tr). */
    const vndAxis = (extra = {}) => ({ ticks: { callback: (v) => formatVndShort(v) }, grid: { color: COLORS.grid }, border: { display: false }, ...extra });

    window.BP = {
        API_BASE, HOME_PAGE, api, getSession, saveSession, clearSession, logout,
        isAdmin: () => getSession()?.role === "admin",
        icon, escapeHtml, safeUrl, toNumber, formatNumber, formatVnd, formatVndShort, formatPercent, formatRating, formatDate,
        normalizeText, parseReviewDate, PRICE_BANDS, priceBand, DISCOUNT_BANDS, discountBucket, median, average, mostCommon,
        debounce, groupReviews, notifyProductsUpdated, onProductsUpdated,
        renderPagination, toast, stateHtml, downloadCsv,
        COLORS, RETAILER_NAMES, retailerKey, retailerColor, chart, vndAxis
    };
    window.logout = logout;

    // ---------------------------------------------------------------- bảo vệ trang
    if (isLoginPage) return;

    const session = getSession();
    if (!session) {
        location.replace(LOGIN_PAGE);
        return;
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => renderShell(session));
    else renderShell(session);

    // Xác thực token với backend (token mất khi backend khởi động lại); cập nhật vai trò thật từ server.
    api("/api/me").then((data) => {
        const role = String(data.user?.role || "user").toLowerCase();
        if (role !== session.role) {
            saveSession(session.token, data.user);
            location.reload();
        }
    }).catch(() => { /* 401 đã tự chuyển về login; lỗi mạng để trang tự báo */ });
})();
