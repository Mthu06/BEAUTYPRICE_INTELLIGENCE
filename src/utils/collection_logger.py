
"""Shared collection logger for BEAUTYPRICE_INTELLIGENCE.

One CollectionLogger instance represents one script execution.
It appends events to output/logs/collection_events.jsonl.
It does not collect data or access websites.
"""

from __future__ import annotations

import json
import os
import socket
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


# Project root: BEAUTYPRICE_INTELLIGENCE/
PROJECT_ROOT = Path(__file__).resolve().parents[2]

EVENT_LOG = (
    PROJECT_ROOT
    / "output"
    / "logs"
    / "collection_events.jsonl"
)


def local_timestamp() -> str:
    """Return local time with timezone information."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


class CollectionLogger:
    """Append-only logger for one collector/parser execution."""

    def __init__(
        self,
        *,
        retailer_id: str,
        category: str,
        stage: str,
        script_name: str,
        output_file: str | None = None,
        log_file: Path | None = None,
    ) -> None:
        now = datetime.now().astimezone()

        self.run_id = (
            f"run_{now.strftime('%Y%m%dT%H%M%S')}_"
            f"{uuid.uuid4().hex[:8]}"
        )

        self.retailer_id = retailer_id.strip().lower()
        self.category = category.strip().lower()
        self.stage = stage.strip().lower()
        self.script_name = script_name
        self.output_file = output_file

        self.log_file = log_file or EVENT_LOG
        self.started_at = local_timestamp()
        self.finished_at: str | None = None

        self.pages_attempted = 0
        self.pages_saved = 0
        self.records_found = 0
        self.records_saved = 0
        self.records_failed = 0
        self.records_skipped = 0

        self._closed = False

        self._write_event(
            event="run_started",
            status="running",
            hostname=socket.gethostname(),
            process_id=os.getpid(),
        )

    def _write_event(
        self,
        *,
        event: str,
        status: str,
        **extra: Any,
    ) -> None:
        """Append one event as a JSON line."""
        self.log_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        record = {
            "event_at": local_timestamp(),
            "event": event,
            "run_id": self.run_id,
            "retailer_id": self.retailer_id,
            "category": self.category,
            "stage": self.stage,
            "script_name": self.script_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": status,
            "pages_attempted": self.pages_attempted,
            "pages_saved": self.pages_saved,
            "records_found": self.records_found,
            "records_saved": self.records_saved,
            "records_failed": self.records_failed,
            "records_skipped": self.records_skipped,
            "output_file": self.output_file,
        }

        record.update(extra)

        with self.log_file.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )

    def page_attempted(self, count: int = 1) -> None:
        """Record pages attempted."""
        self.pages_attempted += max(0, int(count))
        self._write_event(
            event="progress",
            status="running",
        )

    def page_saved(
        self,
        count: int = 1,
        output_file: str | None = None,
    ) -> None:
        """Record pages saved successfully."""
        self.pages_saved += max(0, int(count))

        if output_file:
            self.output_file = output_file

        self._write_event(
            event="progress",
            status="running",
        )

    def records_found_add(self, count: int) -> None:
        """Add the number of records found."""
        self.records_found += max(0, int(count))
        self._write_event(
            event="progress",
            status="running",
        )

    def records_saved_add(self, count: int) -> None:
        """Add the number of records saved successfully."""
        self.records_saved += max(0, int(count))
        self._write_event(
            event="progress",
            status="running",
        )

    def records_failed_add(
        self,
        count: int = 1,
        error_message: str | None = None,
    ) -> None:
        """Add failed records and optionally record an error."""
        self.records_failed += max(0, int(count))

        self._write_event(
            event="error" if error_message else "progress",
            status="running",
            error_message=error_message,
        )

    def records_skipped_add(
        self,
        count: int = 1,
        reason: str | None = None,
    ) -> None:
        """Add intentionally skipped records."""
        self.records_skipped += max(0, int(count))

        self._write_event(
            event="progress",
            status="running",
            skip_reason=reason,
        )

    def finish(
        self,
        status: str = "success",
        error_message: str | None = None,
    ) -> None:
        """Finish the run and append its final event."""
        if self._closed:
            return

        allowed_statuses = {
            "success",
            "partial",
            "failed",
            "interrupted",
        }

        if status not in allowed_statuses:
            raise ValueError(
                f"status must be one of {sorted(allowed_statuses)}"
            )

        self.finished_at = local_timestamp()

        self._write_event(
            event="run_finished",
            status=status,
            error_message=error_message,
        )

        self._closed = True

    def __enter__(self) -> "CollectionLogger":
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_value: Any,
        traceback: Any,
    ) -> bool:
        if exc_value is not None:
            self.finish(
                status="failed",
                error_message=(
                    f"{type(exc_value).__name__}: {exc_value}"
                ),
            )
            return False

        if not self._closed:
            status = (
                "partial"
                if self.records_failed > 0
                else "success"
            )
            self.finish(status=status)

        return False

