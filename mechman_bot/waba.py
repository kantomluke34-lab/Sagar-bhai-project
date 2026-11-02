"""Official Meta WhatsApp Cloud API client."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx

from .config import Settings


class WABAError(RuntimeError):
    pass


class WABAClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = f"https://graph.facebook.com/{settings.meta_api_version}"

    @property
    def configured(self) -> bool:
        return self.settings.waba_configured

    def validate_signature(self, body: bytes, signature: str | None) -> bool:
        if not self.settings.meta_app_secret:
            return True
        if not signature or not signature.startswith("sha256="):
            return False
        expected = hmac.new(
            self.settings.meta_app_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(signature.removeprefix("sha256="), expected)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.meta_access_token:
            raise WABAError("META_ACCESS_TOKEN is not configured")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/{path.lstrip('/')}",
                headers={"Authorization": f"Bearer {self.settings.meta_access_token}"},
                json=payload,
            )
        if response.is_error:
            raise WABAError(f"Meta API {response.status_code}: {response.text}")
        return response.json()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.settings.meta_access_token:
            raise WABAError("META_ACCESS_TOKEN is not configured")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.base_url}/{path.lstrip('/')}",
                headers={"Authorization": f"Bearer {self.settings.meta_access_token}"},
                params=params,
            )
        if response.is_error:
            raise WABAError(f"Meta API {response.status_code}: {response.text}")
        return response.json()

    async def send_text(self, phone: str, message: str) -> str:
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

    async def send_template(
        self,
        phone: str,
        name: str,
        language: str,
        parameters: list[str] | None = None,
    ) -> str:
        components: list[dict[str, Any]] = []
        if parameters:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": value} for value in parameters],
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

    async def submit_template(self, template: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.meta_waba_id:
            raise WABAError("META_WABA_ID is not configured")
        components: list[dict[str, Any]] = []
        if template.get("header"):
            components.append({"type": "HEADER", "format": "TEXT", "text": template["header"]})
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
