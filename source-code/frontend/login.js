/* login.js - trang Đăng nhập. */
document.addEventListener("DOMContentLoaded", () => {
    if (BP.getSession()) {
        location.replace(BP.HOME_PAGE);
        return;
    }

    const $ = (id) => document.getElementById(id);
    const form = $("loginForm");
    const username = $("username");
    const password = $("password");
    const button = $("loginButton");
    const error = $("loginError");
    const toggle = $("togglePassword");

    document.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = BP.icon(el.dataset.icon); });

    // Số liệu thật từ CSDL (không cần đăng nhập, chỉ là con số tổng); lỗi -> ẩn khung thay vì hiện số sai
    BP.api("/api/public-stats", { auth: false }).then((stats) => {
        document.querySelectorAll("[data-stat]").forEach((dd) => { dd.textContent = BP.formatNumber(stats[dd.dataset.stat]); });
        const list = stats.by_retailer || [], max = Math.max(1, ...list.map((r) => r.products));
        $("retailerBars").innerHTML = list.map((r) => `<div class="auth-bar">
            <span class="auth-bar-name"><i style="background:${BP.retailerColor(r.retailer_id)}"></i>${BP.escapeHtml(r.retailer_name)}</span>
            <span class="auth-bar-track"><span class="auth-bar-fill" data-width="${(r.products / max) * 100}" style="background:${BP.retailerColor(r.retailer_id)}"></span></span>
            <span class="auth-bar-value">${BP.formatNumber(r.products)}</span></div>`).join("");
        requestAnimationFrame(() => document.querySelectorAll(".auth-bar-fill").forEach((bar) => { bar.style.width = `${bar.dataset.width}%`; }));
    }).catch(() => { $("authPreview").hidden = true; });

    toggle.innerHTML = BP.icon("eye");
    toggle.addEventListener("click", () => {
        const show = password.type === "password";
        password.type = show ? "text" : "password";
        toggle.classList.toggle("active", show);
        toggle.setAttribute("aria-pressed", String(show));
        toggle.setAttribute("aria-label", show ? "Ẩn mật khẩu" : "Hiện mật khẩu");
    });

    // Tài khoản demo: điền sẵn vào form
    document.querySelectorAll(".demo-account").forEach((btn) => btn.addEventListener("click", () => {
        username.value = btn.dataset.user;
        password.value = btn.dataset.pass;
        error.textContent = "";
        button.focus();
    }));

    const setBusy = (busy) => {
        button.disabled = busy;
        button.textContent = busy ? "Đang đăng nhập..." : "Đăng nhập";
    };

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        error.textContent = "";
        if (!username.value.trim() || !password.value) {
            error.textContent = "Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.";
            (username.value.trim() ? password : username).focus();
            return;
        }

        setBusy(true);
        try {
            const data = await BP.api("/api/login", {
                method: "POST",
                auth: false,
                body: { username: username.value.trim(), password: password.value }
            });
            BP.saveSession(data.token, data.user);
            location.replace(BP.HOME_PAGE);
        } catch (err) {
            error.textContent = err.message;
            setBusy(false);
        }
    });
});
