"""WABA campaign imports, personalization, and background delivery."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from xlrd import open_workbook

from .repository import CRMRepository
from .waba import WABAClient

LOGGER = logging.getLogger(__name__)
PHONE_HINTS = {"phone", "mobile", "number", "whatsapp", "contact", "cell", "tel", "mob"}
MAX_IMPORT_ROWS = 10_000


def normalize_phone(value: Any) -> str:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return digits if 7 <= len(digits) <= 15 else ""


def detect_phone_column(columns: list[str], rows: list[dict[str, str]]) -> str | None:
    for column in columns:
        lowered = column.lower().replace("_", " ").replace("-", " ")
        if any(hint in lowered.split() for hint in PHONE_HINTS):
            return column
    for column in columns:
        sample = [row.get(column, "") for row in rows[:20] if row.get(column, "")]
        if sample and sum(bool(normalize_phone(value)) for value in sample) / len(sample) >= 0.8:
            return column
    return None


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value).strip()


def parse_recipient_file(filename: str, content: bytes) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        columns = [str(column or "").strip() for column in (reader.fieldnames or [])]
        rows = [
            {str(key or "").strip(): _stringify(value) for key, value in row.items()}
            for row in reader
        ]
    elif suffix in {".xlsx", ".xlsm"}:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        iterator = sheet.iter_rows(values_only=True)
        header = next(iterator, ())
        columns = [_stringify(value) or f"column_{index + 1}" for index, value in enumerate(header)]
        rows = [
            {columns[index]: _stringify(value) for index, value in enumerate(values)}
            for values in iterator
        ]
        workbook.close()
    elif suffix == ".xls":
        workbook = open_workbook(file_contents=content)
        sheet = workbook.sheet_by_index(0)
        if sheet.nrows == 0:
            raise ValueError("The uploaded file has no header row")
        columns = [
            _stringify(sheet.cell_value(0, index)) or f"column_{index + 1}"
            for index in range(sheet.ncols)
        ]
        rows = [
            {
                columns[index]: _stringify(sheet.cell_value(row_index, index))
                for index in range(sheet.ncols)
            }
            for row_index in range(1, sheet.nrows)
        ]
    else:
        raise ValueError("Upload a CSV, XLS, or XLSX file")
    if not columns:
        raise ValueError("The uploaded file has no header row")
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValueError(f"Imports are limited to {MAX_IMPORT_ROWS:,} rows")
    rows = [row for row in rows if any(value for value in row.values())]
    phone_column = detect_phone_column(columns, rows)
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "phone_column": phone_column,
        "valid_phone_count": sum(
            bool(normalize_phone(row.get(phone_column, ""))) for row in rows
        )
        if phone_column
        else 0,
    }


def render_parameters(mapping: list[str], variables: dict[str, Any]) -> list[str]:
    lowered = {str(key).lower(): _stringify(value) for key, value in variables.items()}
    rendered: list[str] = []
    for key in mapping:
        value = lowered.get(str(key).lower(), "")
        if not value:
            raise ValueError(f"Missing value for template variable: {key}")
        rendered.append(value)
    return rendered


class CampaignScheduler:
    """Persistent campaign worker. PostgreSQL remains the source of truth."""

    def __init__(
        self,
        repository: CRMRepository,
        waba: WABAClient,
        media_root: str,
        poll_seconds: int = 10,
    ) -> None:
        self.repository = repository
        self.waba = waba
        self.media_root = Path(media_root)
        self.poll_seconds = max(5, poll_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        self.media_root.mkdir(parents=True, exist_ok=True)
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="waba-campaign-scheduler")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                claimed = await self.repository.claim_due_campaign()
                if claimed:
                    await self._deliver(claimed)
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("campaign_worker_failed", extra={"event": "campaign_worker_failed"})
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                pass

    async def _deliver(self, claimed: dict[str, Any]) -> None:
        campaign = claimed["campaign"]
        run = claimed["run"]
        template = claimed["template"]
        asset = claimed.get("asset")
        media_id: str | None = None
        if template.get("header_format") in {"IMAGE", "VIDEO", "DOCUMENT"}:
            if not asset:
                await self.repository.fail_campaign_run(
                    campaign["id"], run["id"], "Approved media template requires an uploaded file"
                )
                return
            # Media IDs are not permanent. Re-upload from the durable source
            # file for every run so weekly recurring campaigns cannot age out.
            path = self.media_root / asset["storage_name"]
            media_id = await self.waba.upload_media(path, asset["mime_type"])
            await self.repository.set_asset_meta_id(asset["id"], media_id)

        for delivery in claimed["deliveries"]:
            state = await self.repository.campaign_status(campaign["id"])
            if state in {"paused", "cancelled"}:
                await self.repository.interrupt_campaign_run(campaign["id"], run["id"], state)
                return
            try:
                parameters = render_parameters(
                    campaign.get("parameter_mapping", []), delivery["variables"]
                )
                wa_id = await self.waba.send_template(
                    delivery["phone"],
                    template["name"],
                    template["language"],
                    parameters,
                    header_type=template.get("header_format"),
                    header_media_id=media_id,
                    header_filename=asset.get("original_name") if asset else None,
                )
                await self.repository.mark_campaign_delivery(
                    delivery["delivery_id"], "accepted", wa_message_id=wa_id, parameters=parameters
                )
            except Exception as exc:
                await self.repository.mark_campaign_delivery(
                    delivery["delivery_id"], "failed", error=str(exc)[:2000]
                )
            throttle = float(campaign.get("throttle_seconds") or 0)
            if throttle:
                await asyncio.sleep(throttle)
        await self.repository.finish_campaign_run(campaign["id"], run["id"])


def infer_media_type(mime_type: str) -> str | None:
    if mime_type.startswith("image/"):
        return "IMAGE"
    if mime_type.startswith("video/"):
        return "VIDEO"
    if mime_type in {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }:
        return "DOCUMENT"
    guessed = mimetypes.guess_extension(mime_type)
    return "DOCUMENT" if guessed else None
