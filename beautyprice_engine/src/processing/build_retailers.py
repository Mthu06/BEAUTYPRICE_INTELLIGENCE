"""
Build retailers.csv as a standalone step for BEAUTYPRICE_INTELLIGENCE.

Run from the project root:
    python src/processing/build_retailers.py

Optional:
    python src/processing/build_retailers.py --output data/processed/retailers.csv

The script derives retailer IDs and category coverage from the INPUTS configuration
in build_beautyprice_datasets.py when available. Website URLs are maintained in
WEBSITE_URLS below.
"""

from __future__ import annotations

import argparse
import ast
import csv
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "processed" / "retailers.csv"
BUILD_SCRIPT = PROJECT_ROOT / "src" / "processing" / "build_beautyprice_datasets.py"

WEBSITE_URLS = {
    "hasaki": "https://hasaki.vn/",
    "guardian": "https://www.guardian.com.vn/",
    "the_gioi_skin_food": "https://thegioiskinfood.com/",
    "cocolux": "https://cocolux.com/",
    "watsons": "https://www.watsons.vn/",
}

RETAILER_NAMES = {
    "hasaki": "Hasaki",
    "guardian": "Guardian",
    "the_gioi_skin_food": "The Gioi Skin Food",
    "cocolux": "Cocolux",
    "watsons": "Watsons",
}


def retailer_key(source: str) -> str:
    """Normalize a retailer name to the project's retailer_id convention."""
    key = re.sub(r"[^a-z0-9]+", "_", source.strip().lower()).strip("_")
    return key


def load_input_config(build_script: Path) -> list[dict[str, Any]]:
    """
    Read INPUTS from the existing build script without importing/running its pipeline.
    Expects INPUTS to be a literal list of dictionaries.
    """
    if not build_script.exists():
        raise FileNotFoundError(
            f"Không tìm thấy build script: {build_script}\n"
            "Hãy đặt build_retailers.py trong src/processing/."
        )

    tree = ast.parse(build_script.read_text(encoding="utf-8-sig"), filename=str(build_script))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if "INPUTS" in names:
                # INPUTS may contain path expressions such as INTERIM_DIR / "hasaki" / "...".
                # Evaluate only the simple dictionary/list/string/path-join structure we expect;
                # do not execute or import the build pipeline.
                def resolve(node_value):
                    if isinstance(node_value, ast.Constant):
                        return node_value.value
                    if isinstance(node_value, ast.List):
                        return [resolve(item) for item in node_value.elts]
                    if isinstance(node_value, ast.Tuple):
                        return tuple(resolve(item) for item in node_value.elts)
                    if isinstance(node_value, ast.Dict):
                        return {
                            resolve(key): resolve(value)
                            for key, value in zip(node_value.keys, node_value.values)
                        }
                    if isinstance(node_value, ast.BinOp) and isinstance(node_value.op, ast.Div):
                        left = resolve(node_value.left)
                        right = resolve(node_value.right)
                        if isinstance(left, Path):
                            return left / str(right)
                        if isinstance(left, str):
                            return Path(left) / str(right)
                        raise ValueError("Biểu thức đường dẫn trong INPUTS không được hỗ trợ.")
                    if isinstance(node_value, ast.Name):
                        # Resolve only known directory constants used in INPUTS.
                        if node_value.id in {"INTERIM_DIR", "RAW_DIR", "PROCESSED_DIR"}:
                            return PROJECT_ROOT / "data" / (
                                "interim" if node_value.id == "INTERIM_DIR"
                                else "raw" if node_value.id == "RAW_DIR"
                                else "processed"
                            )
                        raise ValueError(
                            f"Không hỗ trợ biến '{node_value.id}' trong INPUTS."
                        )
                    raise ValueError(
                        f"Kiểu cấu hình INPUTS chưa được hỗ trợ: {type(node_value).__name__}"
                    )

                value = resolve(node.value)
                if not isinstance(value, list):
                    raise ValueError("INPUTS trong build script phải là một list.")
                return value

    raise ValueError(
        f"Không tìm thấy cấu hình INPUTS dạng literal trong {build_script.name}. "
        "Hãy kiểm tra cấu hình INPUTS hoặc cập nhật script này."
    )


def infer_categories(inputs: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Collect configured category names for each retailer."""
    categories: dict[str, set[str]] = {}
    for item in inputs:
        source = str(item.get("source", "")).strip()
        category = str(item.get("category", "")).strip()
        if not source:
            continue
        key = retailer_key(source)
        categories.setdefault(key, set())
        if category:
            categories[key].add(category)
    return categories


def build_rows(inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    categories_by_retailer = infer_categories(inputs)
    rows: list[dict[str, Any]] = []

    for retailer_id in sorted(categories_by_retailer):
        categories = categories_by_retailer[retailer_id]
        retailer_name = RETAILER_NAMES.get(
            retailer_id,
            retailer_id.replace("_", " ").title(),
        )
        rows.append(
            {
                "retailer_id": retailer_id,
                "retailer_name": retailer_name,
                "country": "Vietnam",
                "currency": "VND",
                "website_url": WEBSITE_URLS.get(retailer_id, ""),
                "is_active": True,
                "data_categories": "; ".join(sorted(categories, key=str.casefold)),
            }
        )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Tạo riêng bảng retailers.csv.")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Đường dẫn file CSV đầu ra (mặc định: data/processed/retailers.csv).",
    )
    args = parser.parse_args()

    inputs = load_input_config(BUILD_SCRIPT)
    rows = build_rows(inputs)

    if not rows:
        raise ValueError("Không tạo được retailer nào từ cấu hình INPUTS.")

    output_path = args.output
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "retailer_id",
        "retailer_name",
        "country",
        "currency",
        "website_url",
        "is_active",
        "data_categories",
    ]

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Retailers saved: {len(rows)}")
    print(f"Output: {output_path}")
    for row in rows:
        print(f"- {row['retailer_id']}: {row['retailer_name']} ({len(row['data_categories'].split('; '))} categories)")


if __name__ == "__main__":
    main()

