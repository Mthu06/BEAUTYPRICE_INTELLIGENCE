
"""Build collection_logs.csv from legacy page logs and shared run events.

Run from project root:
    python src/processing/build_collection_logs.py

This script does not launch collectors or access websites.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "output" / "logs"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "collection_logs.csv"

EVENT_LOG_NAME = "collection_events.jsonl"

COLUMNS = [
    "run_id",
    "retailer_id",
    "script_name",
    "started_at",
    "finished_at",
    "pages_attempted",
    "records_found",
    "records_saved",
    "records_failed",
    "records_skipped",
    "status",
    "error_message",
    "output_file",
    "duration_seconds",
]


def parse_time(value: Any) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    try:
        return datetime.fromisoformat(
            str(value).strip().replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None


def retailer_from_path(
    path: Path,
    rows: list[dict[str, Any]],
) -> str:
    for row in rows:
        value = (
            row.get("retailer_id")
            or row.get("source")
            or row.get("retailer")
        )
        if value:
            return re.sub(
                r"[^a-z0-9]+",
                "_",
                str(value).lower(),
            ).strip("_")

    name = path.name.lower()
    for retailer in (
        "thegioiskinfood",
        "guardian",
        "hasaki",
        "cocolux",
        "watsons",
    ):
        if retailer in name:
            return retailer

    return "unknown"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8-sig") as file:
        for line_no, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except json.JSONDecodeError as exc:
                print(
                    f"WARNING: bỏ qua JSON lỗi "
                    f"{path.name}:{line_no}: {exc}"
                )

    return rows


def unique_messages(rows: list[dict[str, Any]]) -> str | Any:
    messages: list[str] = []

    for row in rows:
        message = row.get("error_message") or row.get("error")
        if message and str(message) not in messages:
            messages.append(str(message))

    return " | ".join(messages) if messages else pd.NA


def summarize_legacy_log(
    path: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize a legacy per-page JSONL file as one run."""
    times = [
        parse_time(
            row.get("collected_at")
            or row.get("timestamp")
            or row.get("started_at")
        )
        for row in rows
    ]
    times = [value for value in times if value is not None]

    start = min(times) if times else None

    page_values = {
        str(row["page"])
        for row in rows
        if row.get("page") is not None
        and str(row["page"]).strip()
    }
    pages_attempted = len(page_values) if page_values else len(rows)

    # Card counts are not equivalent to product records saved.
    records_found = (
        sum(
            row["records_found"]
            for row in rows
            if isinstance(row.get("records_found"), (int, float))
        )
        if any(
            isinstance(row.get("records_found"), (int, float))
            for row in rows
        )
        else pd.NA
    )

    records_saved = (
        sum(
            row["records_saved"]
            for row in rows
            if isinstance(row.get("records_saved"), (int, float))
        )
        if any(
            isinstance(row.get("records_saved"), (int, float))
            for row in rows
        )
        else pd.NA
    )

    bad_statuses = {
        "error",
        "failed",
        "failure",
        "stopped_challenge_or_block",
        "no_product_cards",
        "maintenance",
        "challenge/verification",
    }
    statuses = [
        str(row.get("status", "")).lower()
        for row in rows
        if row.get("status")
    ]

    has_failure = any(value in bad_statuses for value in statuses)
    has_success = any(value in {"ok", "success"} for value in statuses)

    if has_failure and has_success:
        status = "partial"
    elif has_failure:
        status = "failed"
    elif statuses and all(
        value in {"ok", "success"} for value in statuses
    ):
        status = "success"
    else:
        status = "unknown"

    failed_rows = [
        row for row in rows
        if str(row.get("status", "")).lower()
        not in {"ok", "success", ""}
    ]

    output_files: list[str] = []
    for row in rows:
        for key in ("output_file", "html_file", "csv_file"):
            value = row.get(key)
            if value and str(value) not in output_files:
                output_files.append(str(value))

    # Legacy page logs do not contain a reliable run finish time.
    return {
        "run_id": (
            f"{path.stem}_"
            f"{start.strftime('%Y%m%dT%H%M%S') if start else 'unknown'}"
        ),
        "retailer_id": retailer_from_path(path, rows),
        "script_name": path.stem,
        "started_at": start.isoformat() if start else pd.NA,
        "finished_at": pd.NA,
        "pages_attempted": pages_attempted,
        "records_found": records_found,
        "records_saved": records_saved,
        "records_failed": len(failed_rows),
        "records_skipped": pd.NA,
        "status": status,
        "error_message": unique_messages(failed_rows),
        "output_file": (
            " | ".join(output_files) if output_files else pd.NA
        ),
        "duration_seconds": pd.NA,
    }


def summarize_event_run(
    run_id: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize all events belonging to one CollectionLogger run."""
    start_events = [
        row for row in rows if row.get("event") == "run_started"
    ]
    finish_events = [
        row for row in rows if row.get("event") == "run_finished"
    ]

    first = start_events[0] if start_events else rows[0]
    last = finish_events[-1] if finish_events else rows[-1]

    start = parse_time(first.get("started_at"))
    if start is None:
        start = parse_time(first.get("event_at"))

    finish = parse_time(last.get("finished_at"))
    if finish is None and finish_events:
        finish = parse_time(last.get("event_at"))

    # Progress events contain cumulative counters. Use the latest values,
    # rather than adding counters from every event.
    latest = rows[-1]

    final_status = (
        str(last.get("status", "unknown")).lower()
        if finish_events
        else "interrupted"
    )
    if final_status not in {
        "success", "partial", "failed", "interrupted"
    }:
        final_status = "unknown"

    output_file = latest.get("output_file")
    if not output_file:
        output_file = next(
            (
                row.get("output_file")
                for row in reversed(rows)
                if row.get("output_file")
            ),
            None,
        )

    duration = (
        (finish - start).total_seconds()
        if start is not None and finish is not None
        else pd.NA
    )

    return {
        "run_id": run_id,
        "retailer_id": latest.get("retailer_id", first.get("retailer_id", "unknown")),
        "script_name": latest.get("script_name", first.get("script_name", "unknown")),
        "started_at": start.isoformat() if start else pd.NA,
        "finished_at": finish.isoformat() if finish else pd.NA,
        "pages_attempted": latest.get("pages_attempted", pd.NA),
        "records_found": latest.get("records_found", pd.NA),
        "records_saved": latest.get("records_saved", pd.NA),
        "records_failed": latest.get("records_failed", pd.NA),
        "records_skipped": latest.get("records_skipped", pd.NA),
        "status": final_status,
        "error_message": unique_messages(rows),
        "output_file": output_file if output_file else pd.NA,
        "duration_seconds": duration,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build collection_logs.csv from legacy logs and run events."
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=LOG_DIR,
        help="Directory containing JSONL logs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help="Summary CSV output path.",
    )
    args = parser.parse_args()

    if not args.log_dir.exists():
        print(f"No log directory found: {args.log_dir}")
        return 1

    log_files = sorted(args.log_dir.glob("*.jsonl"))
    if not log_files:
        print(f"No JSONL logs found in: {args.log_dir}")
        return 1

    summaries: list[dict[str, Any]] = []
    event_rows_by_run: dict[str, list[dict[str, Any]]] = {}

    for path in log_files:
        rows = read_jsonl(path)
        if not rows:
            continue

        if path.name == EVENT_LOG_NAME:
            for row in rows:
                run_id = row.get("run_id")
                if run_id:
                    event_rows_by_run.setdefault(
                        str(run_id), []
                    ).append(row)
        else:
            summaries.append(summarize_legacy_log(path, rows))

    for run_id, rows in event_rows_by_run.items():
        summaries.append(summarize_event_run(run_id, rows))

    if not summaries:
        print("No valid JSONL records found; CSV was not created.")
        return 1

    output = pd.DataFrame(summaries, columns=COLUMNS)
    output = output.sort_values(
        by=["started_at", "retailer_id", "script_name"],
        na_position="last",
        kind="stable",
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False, encoding="utf-8-sig")

    print("COLLECTION LOG SUMMARY BUILT")
    print(f"JSONL files read: {len(log_files)}")
    print(f"Runs summarized: {len(output)}")
    print(f"Output: {args.output}")
    print("Missing source values remain blank; no outcomes are fabricated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

