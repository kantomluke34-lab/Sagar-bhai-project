"""Official Meta WhatsApp Cloud API client."""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx

from .config import Settings


class WABAError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: int | None = None,
        subcode: int | None = None,
        http_status: int | None = None,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.http_status = http_status
        self.outcome_unknown = outcome_unknown

    @property
    def is_throttle(self) -> bool:
        return self.http_status == 429 or self.code in {
            4,
            17,
            32,
            613,
            80008,
            130429,
            131048,
        }


def _response_error(response: httpx.Response, prefix: str = "Meta API") -> WABAError:
    try:
        error = response.json().get("error", {})
    except (ValueError, AttributeError):
        error = {}
    details = error.get("error_data", {}).get("details")
    message = (
        details or error.get("message") or f"Request failed with status {response.status_code}"
    )
    return WABAError(
        f"{prefix} {response.status_code}: {message}",
        code=error.get("code"),
        subcode=error.get("error_subcode"),
        http_status=response.status_code,
    )


class WABAClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = f"https://graph.facebook.com/{settings.meta_api_version}"
        self._on_throttle: Callable[[str], Awaitable[None]] | None = None
        self._is_throttled: Callable[[], Awaitable[bool]] | None = None

    def set_throttle_hooks(
        self,
        on_throttle: Callable[[str], Awaitable[None]],
        is_throttled: Callable[[], Awaitable[bool]],
    ) -> None:
        self._on_throttle = on_throttle
        self._is_throttled = is_throttled

    async def _ensure_sender_ready(self) -> None:
        if self._is_throttled and await self._is_throttled():
            raise WABAError(
                "Meta temporarily limited this sender. Try again after the cooldown.",
                http_status=429,
            )

    @property
    def configured(self) -> bool:
        return self.settings.waba_configured

    def validate_signature(self, body: bytes, signature: str | None) -> bool:
        if not self.settings.meta_app_secret:
            return False
        if not signature or not signature.startswith("sha256="):
            return False
        expected = hmac.new(
            self.settings.meta_app_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature.removeprefix("sha256="), expected)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.meta_access_token:
            raise WABAError("META_ACCESS_TOKEN is not configured")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/{path.lstrip('/')}",
                    headers={"Authorization": f"Bearer {self.settings.meta_access_token}"},
                    json=payload,
                )
        except httpx.RequestError as exc:
            raise WABAError(
                "Meta API request could not be completed", outcome_unknown=True
            ) from exc
        if response.is_error:
            error = _response_error(response)
            if error.is_throttle and self._on_throttle:
                await self._on_throttle(str(error))
            raise error
        return response.json()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.settings.meta_access_token:
            raise WABAError("META_ACCESS_TOKEN is not configured")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    f"{self.base_url}/{path.lstrip('/')}",
                    headers={"Authorization": f"Bearer {self.settings.meta_access_token}"},
                    params=params,
                )
        except httpx.RequestError as exc:
            raise WABAError("Meta API request could not be completed") from exc
        if response.is_error:
            raise _response_error(response)
        return response.json()

    async def account_health(self) -> dict[str, Any]:
        """Return live sender health and the business-wide 24-hour messaging tier."""
        if not self.settings.meta_waba_id or not self.settings.meta_phone_number_id:
            raise WABAError("WABA and phone number IDs are not configured")
        account = await self._get(
            self.settings.meta_waba_id,
            {"fields": "status,whatsapp_business_manager_messaging_limit"},
        )
        phone = await self._get(
            self.settings.meta_phone_number_id,
            {"fields": "display_phone_number,verified_name,quality_rating,name_status,status"},
        )
        return {
            "waba_status": account.get("status"),
            "messaging_limit_tier": account.get("whatsapp_business_manager_messaging_limit"),
            "display_phone_number": phone.get("display_phone_number"),
            "verified_name": phone.get("verified_name"),
            "quality_rating": phone.get("quality_rating"),
            "name_status": phone.get("name_status"),
            "phone_status": phone.get("status"),
        }

    async def send_text(self, phone: str, message: str) -> str:
        await self._ensure_sender_ready()
        response = await self._post(
            f"{self.settings.meta_phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone,
                "type": "text",
                "text": {"preview_url": False, "body": message},
            },
        )
        return str(response.get("messages", [{}])[0].get("id", ""))

    async def send_reply_buttons(
        self, phone: str, message: str, buttons: list[dict[str, str]]
    ) -> str:
        await self._ensure_sender_ready()
        if not 1 <= len(buttons) <= 3:
            raise WABAError("WhatsApp reply messages require 1-3 buttons")
        response = await self._post(
            f"{self.settings.meta_phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": message},
                    "action": {
                        "buttons": [
                            {
                                "type": "reply",
                                "reply": {"id": button["payload"], "title": button["title"]},
                            }
                            for button in buttons
                        ]
                    },
                },
            },
        )
        return str(response.get("messages", [{}])[0].get("id", ""))

    async def send_template(
        self,
        phone: str,
        name: str,
        language: str,
        parameters: list[str] | None = None,
        *,
        header_type: str | None = None,
        header_media_id: str | None = None,
        header_filename: str | None = None,
        quick_reply_payloads: list[str] | None = None,
    ) -> str:
        await self._ensure_sender_ready()
        components: list[dict[str, Any]] = []
        normalized_header = str(header_type or "").upper()
        if normalized_header in {"IMAGE", "VIDEO", "DOCUMENT"}:
            if not header_media_id:
                raise WABAError(f"{normalized_header.title()} template requires uploaded media")
            media_value: dict[str, str] = {"id": header_media_id}
            if normalized_header == "DOCUMENT" and header_filename:
                media_value["filename"] = header_filename
            components.append(
                {
                    "type": "header",
                    "parameters": [
                        {"type": normalized_header.lower(), normalized_header.lower(): media_value}
                    ],
                }
            )
        if parameters:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": value} for value in parameters],
                }
            )
        for index, payload in enumerate(quick_reply_payloads or []):
            components.append(
                {
                    "type": "button",
                    "sub_type": "quick_reply",
                    "index": str(index),
                    "parameters": [{"type": "payload", "payload": payload}],
                }
            )
        response = await self._post(
            f"{self.settings.meta_phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "to": phone,
                "type": "template",
                "template": {
                    "name": name,
                    "language": {"code": language},
                    **({"components": components} if components else {}),
                },
            },
        )
        return str(response.get("messages", [{}])[0].get("id", ""))

    async def upload_media(self, path: Path, mime_type: str) -> str:
        if not self.settings.meta_access_token:
            raise WABAError("META_ACCESS_TOKEN is not configured")
        if not path.is_file():
            raise WABAError("Campaign media file is missing")
        async with httpx.AsyncClient(timeout=90) as client:
            with path.open("rb") as handle:
                response = await client.post(
                    f"{self.base_url}/{self.settings.meta_phone_number_id}/media",
                    headers={"Authorization": f"Bearer {self.settings.meta_access_token}"},
                    data={"messaging_product": "whatsapp", "type": mime_type},
                    files={"file": (path.name, handle, mime_type)},
                )
        if response.is_error:
            raise WABAError(f"Meta media upload {response.status_code}: {response.text}")
        media_id = str(response.json().get("id", ""))
        if not media_id:
            raise WABAError("Meta media upload did not return an id")
        return media_id

    async def upload_template_header_sample(
        self, content: bytes, mime_type: str, filename: str
    ) -> str:
        """Upload a sample file used only during Meta template review."""
        if not self.settings.meta_access_token:
            raise WABAError("META_ACCESS_TOKEN is not configured")
        if not self.settings.meta_app_id:
            raise WABAError("META_APP_ID is not configured")
        async with httpx.AsyncClient(timeout=90) as client:
            start = await client.post(
                f"{self.base_url}/{self.settings.meta_app_id}/uploads",
                headers={"Authorization": f"Bearer {self.settings.meta_access_token}"},
                params={
                    "file_length": str(len(content)),
                    "file_type": mime_type,
                    "file_name": Path(filename).name[:255],
                },
            )
            if start.is_error:
                raise WABAError(f"Meta template sample upload {start.status_code}: {start.text}")
            upload_id = str(start.json().get("id", ""))
            if not upload_id:
                raise WABAError("Meta template sample upload did not return an upload id")
            upload = await client.post(
                f"{self.base_url}/{upload_id}",
                headers={
                    "Authorization": f"Bearer {self.settings.meta_access_token}",
                    "file_offset": "0",
                    "Content-Type": "application/octet-stream",
                },
                content=content,
            )
        if upload.is_error:
            raise WABAError(f"Meta template sample upload {upload.status_code}: {upload.text}")
        handle = str(upload.json().get("h", ""))
        if not handle:
            raise WABAError("Meta template sample upload did not return a file handle")
        return handle

    async def submit_template(self, template: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.meta_waba_id:
            raise WABAError("META_WABA_ID is not configured")
        components: list[dict[str, Any]] = []
        header_format = str(template.get("header_format") or "NONE").upper()
        if header_format == "NONE" and template.get("header"):
            header_format = "TEXT"
        if header_format == "TEXT":
            components.append({"type": "HEADER", "format": "TEXT", "text": template["header"]})
        elif header_format in {"IMAGE", "VIDEO", "DOCUMENT"}:
            handle = str(template.get("header_sample_handle") or "")
            if not handle:
                raise WABAError("Media header requires a sample file before submission")
            components.append(
                {
                    "type": "HEADER",
                    "format": header_format,
                    "example": {"header_handle": [handle]},
                }
            )
        body_component: dict[str, Any] = {"type": "BODY", "text": template["body"]}
        if template.get("variables"):
            body_component["example"] = {"body_text": [template["variables"]]}
        components.append(body_component)
        if template.get("footer"):
            components.append({"type": "FOOTER", "text": template["footer"]})
        if template.get("buttons"):
            components.append({"type": "BUTTONS", "buttons": template["buttons"]})
        return await self._post(
            f"{self.settings.meta_waba_id}/message_templates",
            {
                "name": template["name"],
                "language": template["language"],
                "category": template["category"],
                "components": components,
                "allow_category_change": True,
            },
        )

    async def list_meta_templates(self) -> list[dict[str, Any]]:
        if not self.settings.meta_waba_id:
            raise WABAError("META_WABA_ID is not configured")
        response = await self._get(
            f"{self.settings.meta_waba_id}/message_templates",
            {"fields": "id,name,status,language,category,rejected_reason,components", "limit": 250},
        )
        return list(response.get("data", []))

    async def find_meta_template(self, name: str, language: str) -> dict[str, Any] | None:
        if not self.settings.meta_waba_id:
            raise WABAError("META_WABA_ID is not configured")
        response = await self._get(
            f"{self.settings.meta_waba_id}/message_templates",
            {
                "fields": "id,name,status,language,category,rejected_reason,components",
                "name": name,
                "limit": 20,
            },
        )
        return next(
            (
                item
                for item in response.get("data", [])
                if item.get("name") == name and item.get("language") == language
            ),
            None,
        )
