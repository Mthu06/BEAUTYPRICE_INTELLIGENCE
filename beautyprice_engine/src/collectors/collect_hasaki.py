# Tạo script thu thập trang 1–9 

from pathlib import Path
from time import sleep
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser
from urllib.request import Request, urlopen
from datetime import datetime
import json

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


# ==========================================
# 1. CAU HINH DU AN
# ==========================================

# File nam tai: src/collectors/collect_hasaki.py
# parents[2] tro den thu muc goc BEAUTYPRICE_INTELLIGENCE.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

BASE_URL = "https://hasaki.vn"
CATEGORY_PATH = "/danh-muc/chong-nang-da-mat-c11.html"

START_PAGE = 1
END_PAGE = 9

# Luu HTML goc, khong chinh sua noi dung HTML.
DATA_DIR = PROJECT_ROOT / "data/raw/hasaki/html"

# Luu nhat ky thu thap.
LOG_FILE = (
    PROJECT_ROOT
    / "output/logs/hasaki_collection_log.jsonl"
)

WAIT_SECONDS = 20
DELAY_BETWEEN_PAGES = 3


# ==========================================
# 2. KIEM TRA ROBOTS.TXT
# ==========================================

def check_robots():
    robots_url = urljoin(BASE_URL, "/robots.txt")

    print("Dang kiem tra:", robots_url)

    request = Request(
        robots_url,
        headers={"User-Agent": "Mozilla/5.0"},
    )

    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            content = response.read().decode(
                "utf-8",
                errors="replace",
            )

    except Exception as exc:
        raise RuntimeError(
            "Khong the xac minh robots.txt. "
            "Dung thu thap cho den khi kiem tra duoc quy tac."
        ) from exc

    if status != 200:
        raise RuntimeError(
            f"robots.txt tra ve HTTP {status}; dung de kiem tra."
        )

    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(content.splitlines())

    print("Da doc robots.txt.")

    for page in range(START_PAGE, END_PAGE + 1):
        url = f"{BASE_URL}{CATEGORY_PATH}?p={page}"

        if not parser.can_fetch("*", url):
            raise RuntimeError(
                f"robots.txt khong cho phep thu thap: {url}"
            )

    print(
        "Robots.txt khong chan cac URL trang dang kiem tra."
    )


# ==========================================
# 3. HAM HO TRO
# ==========================================

def append_log(data):
    LOG_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(
            json.dumps(data, ensure_ascii=False) + "\n"
        )


def looks_like_challenge(html, page_title):
    text = (
        (page_title or "")
        + "\n"
        + (html or "")[:100000]
    ).lower()

    indicators = [
        "captcha",
        "verify you are human",
        "checking your browser",
        "access denied",
        "unusual traffic",
        "security challenge",
    ]

    return any(
        indicator in text
        for indicator in indicators
    )


def inspect_html(html):
    soup = BeautifulSoup(html, "html.parser")

    cards = soup.select("div.rounded-xl.bg-card")
    product_links = soup.select(
        'a[href*="/san-pham/"]'
    )

    named_cards = 0
    priced_cards = 0

    for card in cards:
        name = card.select_one("h2")
        price = card.select_one(
            "span.text-orange.font-bold"
        )

        if name and name.get_text(" ", strip=True):
            named_cards += 1

        if price and price.get_text(" ", strip=True):
            priced_cards += 1

    return {
        "card_count": len(cards),
        "product_link_count": len(product_links),
        "named_card_count": named_cards,
        "priced_card_count": priced_cards,
    }


# ==========================================
# 4. THU THAP TUAN TU
# ==========================================

def main():
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    LOG_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Neu khong xac minh duoc robots.txt thi khong tiep tuc.
    check_robots()

    options = Options()

    # Mo Chrome co giao dien de quan sat.
    # Khong dung proxy xoay vong hoac stealth mode.
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)

    try:
        for page in range(START_PAGE, END_PAGE + 1):
            url = f"{BASE_URL}{CATEGORY_PATH}?p={page}"

            print(
                f"\n===== TRANG {page}/{END_PAGE} ====="
            )
            print("URL:", url)

            record = {
                "source": "hasaki",
                "page": page,
                "url": url,
                "collected_at": (
                    datetime.now()
                    .astimezone()
                    .isoformat()
                ),
            }

            try:
                driver.get(url)

                WebDriverWait(
                    driver,
                    WAIT_SECONDS,
                ).until(
                    lambda d: d.execute_script(
                        "return document.readyState"
                    ) == "complete"
                )

                # Cho JavaScript render them noi dung.
                sleep(2)

                title = driver.title or ""
                html = driver.page_source

                output_html = (
                    DATA_DIR
                    / f"hasaki_page_{page}.html"
                )

                # Luu HTML truoc khi danh gia trang.
                output_html.write_text(
                    html,
                    encoding="utf-8",
                )

                record.update({
                    "title": title,
                    "html_file": str(
                        output_html.relative_to(
                            PROJECT_ROOT
                        )
                    ),
                    "html_bytes": len(
                        html.encode("utf-8")
                    ),
                })

                # Dung neu phat hien dau hieu CAPTCHA/challenge.
                if looks_like_challenge(html, title):
                    record["status"] = (
                        "stopped_challenge_or_block"
                    )
                    append_log(record)

                    print(
                        "Phat hien dau hieu xac minh/"
                        "chan truy cap. Da luu HTML va dung."
                    )
                    break

                stats = inspect_html(html)
                record.update(stats)

                # Khong tiep tuc neu khong tim thay card.
                if stats["card_count"] == 0:
                    record["status"] = "no_product_cards"
                    append_log(record)

                    print(
                        "Khong tim thay card theo selector "
                        "hien tai. Da luu HTML de kiem tra."
                    )
                    break

                record["status"] = "ok"
                append_log(record)

                print("Tieu de:", title)
                print(
                    "Dung luong HTML:",
                    record["html_bytes"],
                    "bytes",
                )
                print(
                    "So the san pham:",
                    stats["card_count"],
                )
                print(
                    "The co ten:",
                    stats["named_card_count"],
                )
                print(
                    "The co gia:",
                    stats["priced_card_count"],
                )
                print("Da luu:", output_html)

            except Exception as exc:
                record["status"] = "error"
                record["error"] = str(exc)
                append_log(record)

                print("Loi:", exc)
                print(
                    "Dung tai trang nay de kiem tra."
                )
                break

            if page < END_PAGE:
                sleep(DELAY_BETWEEN_PAGES)

    finally:
        driver.quit()

    print("\nHoan tat dot kiem tra.")
    print("Thu muc HTML:", DATA_DIR)
    print("Nhat ky:", LOG_FILE)


if __name__ == "__main__":
    main()
