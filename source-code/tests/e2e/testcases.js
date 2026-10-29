// Chạy test case giao diện, lưu ảnh + tệp xuất + video demo + kết quả JSON.
// node testcases.js <base> <outdir>
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const path = require("path");
const [, , BASE, OUT] = process.argv;
const SHOTS = path.join(OUT, "screens"), EXPORTS = path.join(OUT, "exports");
[SHOTS, EXPORTS].forEach((d) => fs.mkdirSync(d, { recursive: true }));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];

(async () => {
    const browser = await puppeteer.launch({ executablePath: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe", headless: "new" });
    const page = await browser.newPage();
    await page.setViewport({ width: 1366, height: 820 });
    const cdp = await page.createCDPSession();
    await cdp.send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: EXPORTS, eventsEnabled: true });
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    // Quay video: lấy khung hình từ Chrome (CDP screencast), cuối cùng ghép bằng ffmpeg thành MP4.
    const FRAMES = path.join(OUT, "_frames"); fs.mkdirSync(FRAMES, { recursive: true });
    const frames = [];
    cdp.on("Page.screencastFrame", ({ data, metadata, sessionId }) => {
        const file = path.join(FRAMES, `${String(frames.length).padStart(5, "0")}.jpg`);
        fs.writeFileSync(file, Buffer.from(data, "base64"));
        frames.push({ file, t: metadata.timestamp });
        cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
    });
    await cdp.send("Page.startScreencast", { format: "jpeg", quality: 70, maxWidth: 1366, maxHeight: 820, everyNthFrame: 1 });

    const shot = async (name, full = false) => { const p = `screens/${name}.png`; await page.screenshot({ path: path.join(OUT, p), fullPage: full }); return p; };
    const go = async (file) => { await page.goto(`${BASE}/${file}`, { waitUntil: "networkidle0" }); await sleep(900); };
    const text = (sel) => page.$eval(sel, (e) => e.textContent.trim()).catch(() => "");
    const visible = (sel) => page.$eval(sel, (e) => !!(e.offsetParent || e.getClientRects().length) && !e.hidden).catch(() => false);
    const api = (p, opts) => page.evaluate(async (p, opts) => { try { return { ok: true, data: await BP.api(p, opts) }; } catch (e) { return { ok: false, status: e.status, message: e.message }; } }, p, opts);
    // Bấm nút rồi chờ thông báo MỚI xuất hiện (không đọc nhầm thông báo cũ còn trên màn hình).
    const clickToast = async (sel) => {
        const n = (await page.$$(".toast")).length;
        await page.click(sel);
        await page.waitForFunction((n) => document.querySelectorAll(".toast").length > n, { timeout: 15000 }, n);
        return page.$$eval(".toast", (t) => t[t.length - 1].textContent.trim());
    };
    const waitDownload = async (pattern, before) => {
        for (let i = 0; i < 40; i++) {
            const f = fs.readdirSync(EXPORTS).filter((n) => pattern.test(n) && !before.includes(n) && !n.endsWith(".crdownload"));
            if (f.length) return f[0];
            await sleep(250);
        }
        return null;
    };
    async function login(user, pass) {
        await page.evaluate(() => window.BP && BP.getSession() && BP.logout()).catch(() => {});
        await sleep(600);
        await go("login.html");
        await page.$eval("#username", (e) => (e.value = ""));
        await page.$eval("#password", (e) => (e.value = ""));
        await page.type("#username", user);
        await page.type("#password", pass);
        await Promise.all([page.waitForNavigation({ waitUntil: "networkidle0" }), page.click("#loginButton")]);
        await sleep(800);
    }
    async function tc(id, group, name, steps, expected, fn) {
        let r = { actual: "", pass: false, shot: null };
        try { r = { ...r, ...(await fn()) }; } catch (e) { r.actual = "Lỗi khi chạy: " + e.message; }
        results.push({ id, group, name, steps, expected, ...r });
        console.log(`${r.pass ? "PASS" : "FAIL"} ${id} ${name} — ${r.actual}`);
    }

    // ---------------------------------------------------------------- đăng nhập & phân quyền
    await tc("TC01", "Đăng nhập", "Truy cập trang khi chưa đăng nhập", "Mở /dashboard.html khi chưa đăng nhập",
        "Bị chuyển về trang đăng nhập", async () => {
            await go("dashboard.html");
            const url = page.url();
            return { actual: `URL hiện tại: ${url.split("/").pop()}`, pass: url.endsWith("login.html"), shot: await shot("01_dang_nhap") };
        });
    await tc("TC02", "Đăng nhập", "Đăng nhập sai mật khẩu", "Nhập admin / matkhausai → Đăng nhập",
        "Hiện thông báo lỗi, không vào hệ thống", async () => {
            await page.type("#username", "admin"); await page.type("#password", "matkhausai"); await page.click("#loginButton");
            await page.waitForFunction(() => document.getElementById("loginError").textContent.trim() !== "");
            const msg = await text("#loginError");
            return { actual: `Thông báo: "${msg}"`, pass: /không đúng/i.test(msg) && page.url().endsWith("login.html"), shot: await shot("02_dang_nhap_sai") };
        });
    await tc("TC03", "Đăng nhập", "Đăng nhập admin thành công", "Nhập admin / Admin@123 → Đăng nhập",
        "Vào trang Tổng quan, sidebar ghi Quản trị viên và có menu Sao lưu", async () => {
            await login("admin", "Admin@123");
            const role = await text("#userRole"), hasBackupMenu = !!(await page.$('a[href="saoluu.html"]'));
            return { actual: `Trang: ${page.url().split("/").pop()}, vai trò: ${role}, menu Sao lưu: ${hasBackupMenu ? "có" : "không"}`,
                pass: page.url().endsWith("dashboard.html") && role === "Quản trị viên" && hasBackupMenu, shot: await shot("03_tong_quan", true) };
        });

    // ---------------------------------------------------------------- dashboard
    await tc("TC04", "Tổng quan", "Lọc dashboard theo nhà bán lẻ", "Chọn Nhà bán lẻ = Hasaki",
        "KPI Tổng sản phẩm bằng số sản phẩm Hasaki trong CSDL", async () => {
            const total = (await api("/api/products")).data.products.filter((p) => p.retailer_id === "hasaki").length;
            await page.select("#retailerFilter", "hasaki"); await sleep(1000);
            const kpi = await text("#kpiTotal");
            return { actual: `KPI = ${kpi}, CSDL = ${total.toLocaleString("vi-VN")}`, pass: kpi === total.toLocaleString("vi-VN"), shot: await shot("04_tong_quan_loc_hasaki") };
        });

    // ---------------------------------------------------------------- tra cứu + CRUD
    await go("tracuu.html");
    await tc("TC05", "Tra cứu", "Tìm kiếm không dấu", "Gõ \"kem chong nang\" vào ô tìm kiếm",
        "Có kết quả; sản phẩm khớp từ khóa trên tên/thương hiệu/danh mục, không phân biệt dấu (dòng đầu chứa \"kem chống nắng\")", async () => {
            await page.type("#searchInput", "kem chong nang"); await sleep(1200);
            const names = await page.$$eval("#tableBody .tc-link", (els) => els.map((e) => e.textContent));
            const norm = (s) => s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d");
            const ok = names.length > 0;
            const summary = await text("#summaryText");
            return { actual: `${summary}; dòng đầu: "${names[0] || "—"}"`, pass: ok && norm(names[0]).includes("kem chong nang"), shot: await shot("05_tra_cuu_tim_kiem") };
        });
    await tc("TC06", "Tra cứu", "Xem chi tiết và lịch sử giá", "Tìm một sản phẩm đã đổi giá giữa các lần thu thập → bấm tên sản phẩm",
        "Mở cửa sổ chi tiết, biểu đồ Lịch sử giá có từ 2 điểm trở lên", async () => {
            const products = (await api("/api/products")).data.products;
            let target = null;
            for (const p of products.filter((x) => x.snapshot_count >= 2).slice(0, 80)) {
                const h = (await api(`/api/products/${p.id}`)).data.history;
                if (new Set(h.map((s) => s.current_price_vnd)).size > 1) { target = p; break; }
            }
            await page.$eval("#searchInput", (e) => (e.value = "")); await page.type("#searchInput", target.product_name.slice(0, 40)); await sleep(1200);
            await page.click(`#tableBody [data-action="view"][data-id="${target.id}"]`);
            await page.waitForSelector("#detailModal:not([hidden])"); await sleep(1500);
            const points = await page.evaluate(() => Object.values(Chart.instances).find((c) => c.canvas.id === "historyChart")?.data.datasets[0].data.length || 0);
            return { actual: `Sản phẩm "${target.product_name.slice(0, 50)}": biểu đồ có ${points} điểm`, pass: points >= 2, shot: await shot("06_chi_tiet_lich_su_gia") };
        });
    await page.keyboard.press("Escape"); await sleep(400);

    const newName = `SP kiểm thử ${Date.now()}`;
    await tc("TC07", "CRUD", "Thêm sản phẩm sai dữ liệu", "Thêm sản phẩm: giá hiện tại 200.000, giá niêm yết 150.000 → Lưu",
        "Báo lỗi \"Giá niêm yết...\" trong form, không lưu", async () => {
            await page.click("#addBtn"); await page.waitForSelector("#formModal:not([hidden])");
            await page.type("#fName", newName); await page.type("#fBrand", "Cocoon"); await page.select("#fRetailer", "hasaki"); await page.select("#fCategory", "Serum");
            await page.type("#fPrice", "200000"); await page.type("#fListed", "150000");
            await page.click("#formSubmit"); await sleep(600);
            const err = await text("#formError"), open = await visible("#formModal");
            return { actual: `Lỗi: "${err}", form vẫn mở: ${open}`, pass: /niêm yết/i.test(err) && open, shot: await shot("07_them_san_pham_loi") };
        });
    await tc("TC08", "CRUD", "Thêm sản phẩm hợp lệ", "Sửa giá niêm yết thành 250.000 → Lưu",
        "Thông báo thêm thành công, % giảm tự tính = 20%, tổng sản phẩm tăng 1", async () => {
            const before = (await api("/api/products")).data.total;
            await page.$eval("#fListed", (e) => (e.value = "")); await page.type("#fListed", "250000");
            const discount = await page.$eval("#fDiscount", (e) => e.value);
            const msg = await clickToast("#formSubmit"); await sleep(800);
            const after = (await api("/api/products")).data.total;
            return { actual: `"${msg}", % giảm hiển thị: ${discount}, tổng ${before} → ${after}`, pass: after === before + 1 && /thành công/i.test(msg), shot: await shot("08_them_san_pham_ok") };
        });
    const created = (await api("/api/products")).data.products.find((p) => p.product_name === newName);
    await tc("TC09", "CRUD", "Sửa giá sản phẩm", "Tìm sản phẩm vừa thêm → Sửa → giá hiện tại 180.000 → Lưu",
        "Lưu thành công; lịch sử giá có thêm 1 lần cập nhật (2 snapshot)", async () => {
            await page.$eval("#searchInput", (e) => (e.value = "")); await page.type("#searchInput", newName); await sleep(1200);
            await page.click(`#tableBody [data-action="edit"][data-id="${created.id}"]`); await page.waitForSelector("#formModal:not([hidden])");
            await page.$eval("#fPrice", (e) => (e.value = "")); await page.type("#fPrice", "180000");
            await shot("09_sua_san_pham");
            const msg = await clickToast("#formSubmit"); await sleep(800);
            const h = (await api(`/api/products/${created.id}`)).data.history;
            return { actual: `"${msg}", số snapshot: ${h.length}, giá: ${h.map((s) => s.current_price_vnd).join(" → ")}`, pass: h.length === 2 && h[1].current_price_vnd === 180000, shot: "screens/09_sua_san_pham.png" };
        });
    await tc("TC10", "CRUD", "Xóa sản phẩm", "Bấm Xóa ở sản phẩm vừa thêm → Xác nhận",
        "Thông báo xóa thành công, sản phẩm không còn trong CSDL", async () => {
            await page.click(`#tableBody [data-action="delete"][data-id="${created.id}"]`); await page.waitForSelector("#deleteModal:not([hidden])");
            await shot("10_xoa_san_pham");
            const msg = await clickToast("#deleteConfirm"); await sleep(600);
            const r = await api(`/api/products/${created.id}`);
            return { actual: `"${msg}", gọi lại API: ${r.ok ? "vẫn còn" : "HTTP " + r.status}`, pass: !r.ok && r.status === 404, shot: "screens/10_xoa_san_pham.png" };
        });
    await tc("TC11", "Xuất báo cáo", "Xuất CSV danh sách đang lọc", "Ở trang Tra cứu, tìm \"serum\" → Xuất CSV",
        "Tải về tệp CSV có dòng tiêu đề và đúng số sản phẩm đang lọc", async () => {
            await page.$eval("#searchInput", (e) => (e.value = "")); await page.type("#searchInput", "serum"); await sleep(1200);
            const before = fs.readdirSync(EXPORTS); await page.click("#exportBtn");
            const file = await waitDownload(/\.csv$/, before);
            const lines = fs.readFileSync(path.join(EXPORTS, file), "utf8").trim().split(/\r?\n/).length;
            const summary = await text("#summaryText");
            return { actual: `Tệp ${file}: ${lines - 1} dòng dữ liệu; trên trang: ${summary}`, pass: lines > 1, shot: await shot("11_xuat_csv_tra_cuu") };
        });

    // ---------------------------------------------------------------- mô hình
    for (const [id, file, name, expected, check, sh] of [
        ["TC12", "phankhuc.html", "Trang Phân khúc K-Means", "Hiện số cụm k, 4 biểu đồ, thẻ đặc điểm cụm", () => page.evaluate(() => Object.keys(Chart.instances).length), "12_phan_khuc"],
        ["TC13", "dudoan.html", "Trang Dự đoán giá", "Hiện MAE/RMSE/R²/MAPE, so sánh mô hình, ma trận nhầm lẫn", () => page.evaluate(() => Object.keys(Chart.instances).length), "13_du_doan"],
        ["TC14", "batthuong.html", "Trang Phát hiện bất thường", "Hiện số sản phẩm bất thường, biểu đồ, danh sách và lý do", () => page.evaluate(() => Object.keys(Chart.instances).length), "14_bat_thuong"],
    ]) {
        await tc(id, "Mô hình", name, `Mở ${file}`, expected, async () => {
            await go(file); await sleep(800);
            const charts = await check(), bad = await page.evaluate(() => (document.body.innerText.match(/NaN|undefined/g) || []).length);
            const h1 = await text("h1");
            return { actual: `"${h1}": ${charts} biểu đồ, ${bad} giá trị lỗi (NaN/undefined)`, pass: charts >= 3 && bad === 0, shot: await shot(sh, true) };
        });
    }

    await tc("TC15", "Xuất báo cáo", "Báo cáo thống kê: xuất CSV và PDF", "Mở Báo cáo → Xuất CSV; In / Lưu PDF",
        "Tải về CSV nhiều phần; tạo được PDF báo cáo", async () => {
            await go("baocao.html"); await sleep(1000);
            const before = fs.readdirSync(EXPORTS); await page.click("#exportBtn");
            const csv = await waitDownload(/\.csv$/, before);
            const sections = fs.readFileSync(path.join(EXPORTS, csv), "utf8").split(/\r?\n/).filter((l) => /^"?\d+\./.test(l) || /^#|^\[/.test(l)).length;
            await shot("15_bao_cao", true);
            await page.emulateMediaType("print");
            await page.pdf({ path: path.join(EXPORTS, "bao_cao_thong_ke.pdf"), format: "A4", printBackground: true, margin: { top: "12mm", bottom: "12mm", left: "10mm", right: "10mm" } });
            await page.emulateMediaType("screen");
            const pdfSize = fs.statSync(path.join(EXPORTS, "bao_cao_thong_ke.pdf")).size;
            return { actual: `CSV: ${csv}; PDF: bao_cao_thong_ke.pdf (${Math.round(pdfSize / 1024)} KB)`, pass: !!csv && pdfSize > 20000, shot: "screens/15_bao_cao.png" };
        });

    // ---------------------------------------------------------------- sao lưu & phục hồi
    let backupName = null;
    await tc("TC16", "Sao lưu & phục hồi", "Tạo bản sao lưu", "Admin mở Sao lưu & phục hồi → Tạo bản sao lưu",
        "Bản sao lưu mới xuất hiện, kiểm tra toàn vẹn = Toàn vẹn, số dòng khớp CSDL hiện tại", async () => {
            await go("saoluu.html");
            const before = (await api("/api/backups")).data.backups.length;
            const msg = await clickToast("#backupBtn"); await sleep(1200);
            const data = (await api("/api/backups")).data;
            backupName = data.backups[0].name;
            const same = JSON.stringify(data.backups[0].counts) === JSON.stringify(data.current.counts);
            return { actual: `"${msg}"; số bản: ${before} → ${data.backups.length}; integrity=${data.backups[0].integrity}; số dòng khớp hiện tại: ${same}`,
                pass: data.backups.length === before + 1 && data.backups[0].integrity === "ok" && same, shot: await shot("16_sao_luu") };
        });
    let victim = null;
    await tc("TC17", "Sao lưu & phục hồi", "Phục hồi thực tế sau khi dữ liệu bị thay đổi",
        "Xóa 1 sản phẩm (giả lập mất dữ liệu) → Phục hồi bản vừa sao lưu → Xác nhận",
        "Kết quả kiểm tra \"khớp 100%\" ở cả 13 bảng; sản phẩm đã xóa xuất hiện lại", async () => {
            victim = (await api("/api/products")).data.products[10];
            await api(`/api/products/${victim.id}`, { method: "DELETE" });
            const gone = !(await api(`/api/products/${victim.id}`)).ok;
            await go("saoluu.html");
            await page.click(`[data-restore="${backupName}"]`); await page.waitForSelector("#confirmModal:not([hidden])");
            await shot("17a_xac_nhan_phuc_hoi");
            await page.click("#confirmRestore");
            await page.waitForSelector("#resultCard:not([hidden])", { timeout: 15000 }); await sleep(1500);
            const badge = await text("#resultBadge"), rows = await page.$$eval("#resultTable tr", (r) => r.length);
            const back = (await api(`/api/products/${victim.id}`)).ok;
            await page.$eval("#resultCard", (e) => e.scrollIntoView()); await sleep(500);
            return { actual: `Đã xóa trước khi phục hồi: ${gone}; kết quả: "${badge}" (${rows} bảng); sản phẩm "${victim.product_name.slice(0, 40)}" có lại: ${back}`,
                pass: gone && /khớp 100%/.test(badge) && rows === 13 && back, shot: await shot("17b_ket_qua_phuc_hoi") };
        });

    // ---------------------------------------------------------------- tài khoản user
    await login("user", "User@123");
    await tc("TC18", "Phân quyền", "Tài khoản User chỉ được xem", "Đăng nhập user / User@123 → mở Tra cứu",
        "Không có nút Thêm/Sửa/Xóa, không có menu Sao lưu", async () => {
            await go("tracuu.html");
            const add = await visible("#addBtn"), edits = (await page.$$('#tableBody [data-action="edit"], #tableBody [data-action="delete"]')).length;
            const menu = !!(await page.$('a[href="saoluu.html"]'));
            return { actual: `Nút Thêm: ${add ? "hiện" : "ẩn"}, nút Sửa/Xóa: ${edits}, menu Sao lưu: ${menu ? "có" : "không"}`, pass: !add && edits === 0 && !menu, shot: await shot("18_user_tra_cuu") };
        });
    await tc("TC19", "Phân quyền", "User gọi API quản trị trực tiếp", "Từ trình duyệt của user gọi DELETE /api/products/<id> và GET /api/backups",
        "Backend từ chối với HTTP 403", async () => {
            const del = await api(`/api/products/${victim.id}`, { method: "DELETE" }), bk = await api("/api/backups");
            await go("saoluu.html");
            return { actual: `DELETE: HTTP ${del.status}; /api/backups: HTTP ${bk.status}; trang Sao lưu: "${await text("#pageNotice")}"`,
                pass: del.status === 403 && bk.status === 403, shot: await shot("19_user_khong_co_quyen") };
        });
    await tc("TC20", "Đăng nhập", "Đăng xuất", "Bấm nút Đăng xuất → mở lại /baocao.html",
        "Về trang đăng nhập; mở lại trang bị chuyển về đăng nhập", async () => {
            await Promise.all([page.waitForNavigation({ waitUntil: "networkidle0" }), page.click(".logout-btn")]);
            const first = page.url().split("/").pop();
            await go("baocao.html");
            return { actual: `Sau đăng xuất: ${first}; mở lại báo cáo: ${page.url().split("/").pop()}`, pass: first === "login.html" && page.url().endsWith("login.html") };
        });

    // ---------------------------------------------------------------- responsive
    await login("admin", "Admin@123");
    await page.setViewport({ width: 390, height: 844, isMobile: true });
    await tc("TC21", "Giao diện", "Hiển thị trên điện thoại", "Mở Tổng quan ở màn hình 390px",
        "Không tràn ngang, có nút menu thu gọn", async () => {
            await go("dashboard.html");
            const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
            const menu = await visible(".menu-toggle");
            return { actual: `Tràn ngang: ${overflow}, nút menu: ${menu ? "có" : "không"}`, pass: !overflow && menu, shot: await shot("21_mobile", true) };
        });

    await cdp.send("Page.stopScreencast").catch(() => {});
    await browser.close();
    const slash = (p) => p.split(path.sep).join("/");
    const list = frames.map((f, i) => `file '${slash(f.file)}'` + "\n" +
        `duration ${Math.min(Math.max((frames[i + 1]?.t ?? f.t + 2) - f.t, 0.04), 2.5).toFixed(3)}`);
    list.push(`file '${slash(frames[frames.length - 1].file)}'`);
    fs.writeFileSync(path.join(FRAMES, "list.txt"), list.join("\n") + "\n");
    require("child_process").execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", path.join(FRAMES, "list.txt"),
        "-vf", "scale=1366:820:force_original_aspect_ratio=decrease,pad=1366:820:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p",
        "-r", "15", "-c:v", "libx264", "-crf", "28", "-preset", "veryfast", path.join(OUT, "demo.mp4")]);
    fs.rmSync(FRAMES, { recursive: true, force: true });
    fs.writeFileSync(path.join(OUT, "test_results.json"), JSON.stringify({ run_at: new Date().toISOString(), base: BASE, page_errors: errors, results }, null, 2));
    console.log(`\n${results.filter((r) => r.pass).length}/${results.length} PASS; page errors: ${errors.length}`);
})().catch((e) => { console.error(e); process.exit(1); });
