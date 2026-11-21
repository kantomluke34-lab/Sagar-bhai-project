"""Durable execution engine for campaign-specific WhatsApp DM flows."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from .dm_flows import choice_for_reply, edge_target, graph_indexes, render_flow_text
from .repository import CRMRepository
from .waba import WABAClient, WABAError

LOGGER = logging.getLogger(__name__)
EXECUTION_PAYLOAD = re.compile(r"^dmf:(\d+):([a-zA-Z0-9_-]{1,40})$")


class DMFlowEngine:
    def __init__(self, repository: CRMRepository, waba: WABAClient) -> None:
        self.repository = repository
        self.waba = waba

    async def start_for_delivery(
        self, delivery_id: int, root_wa_message_id: str
    ) -> dict[str, Any] | None:
        execution = await self.repository.create_dm_flow_execution(
            delivery_id, root_wa_message_id
        )
        if not execution:
            return None
        bundle = await self.repository.get_dm_flow_execution(execution["id"])
        if not bundle:
            return None
        try:
            return await self._advance(bundle)
        except Exception as exc:
            await self._fail(bundle, exc)
            return await self.repository.get_dm_flow_execution(bundle["id"])

    async def handle_inbound(
        self,
        *,
        phone: str,
        conversation_id: int,
        message_id: str,
        text: str,
        payload: str | None,
        context_message_id: str | None,
    ) -> bool:
        execution_id = None
        if payload:
            match = EXECUTION_PAYLOAD.fullmatch(payload)
            if match:
                execution_id = int(match.group(1))
        execution = await self.repository.claim_dm_flow_inbound(
            phone,
            message_id,
            context_message_id=context_message_id,
            execution_id=execution_id,
            conversation_id=conversation_id,
            text=text,
            payload=payload,
        )
        if not execution:
            return False
        try:
            await self._advance(execution, inbound={"text": text, "payload": payload})
        except Exception as exc:
            await self._fail(execution, exc)
        return True

    async def resume_due(self, execution: dict[str, Any]) -> None:
        try:
            resumed_from = execution.get("resumed_from")
            if resumed_from == "processing_reply":
                pending = dict(execution.get("variables") or {}).get("_pending_inbound") or {}
                await self._advance(execution, inbound=pending)
            else:
                await self._advance(
                    execution,
                    resumed_from=resumed_from if resumed_from not in {"processing_start"} else None,
                )
        except Exception as exc:
            await self._fail(execution, exc)

    async def _advance(
        self,
        execution: dict[str, Any],
        *,
        inbound: dict[str, str | None] | None = None,
        resumed_from: str | None = None,
    ) -> dict[str, Any] | None:
        graph = execution.get("graph")
        if not graph:
            raise ValueError("Published flow graph is unavailable")
        nodes, outgoing = graph_indexes(graph)
        node_id = str(execution["current_node_id"])
        variables = dict(execution.get("variables") or {})

        conversation_id = execution.get("conversation_id")
        if conversation_id:
            conversation = await self.repository.get_conversation(int(conversation_id))
            if conversation and conversation.get("is_taken_over"):
                return await self.repository.set_dm_flow_execution_state(
                    execution["id"],
                    status="handed_off",
                    event_type="human_takeover_detected",
                )

        if inbound is not None:
            variables.pop("_pending_inbound", None)
            node = nodes.get(node_id)
            if not node:
                raise ValueError("Execution references a missing flow node")
            target: str | None
            if node["type"] in {"reply_router", "send_buttons"}:
                choice = choice_for_reply(
                    node, str(inbound.get("text") or ""), inbound.get("payload")
                )
                target = edge_target(outgoing[node_id], choice) if choice else None
                if not target:
                    target = edge_target(outgoing[node_id], "fallback")
                if not target:
                    await self._wait_for_reply(execution["id"], node)
                    await self.repository.add_dm_flow_execution_event(
                        execution["id"],
                        "reply_unmatched",
                        node_id=node_id,
                        details={"text": inbound.get("text") or ""},
                    )
                    return await self.repository.get_dm_flow_execution(execution["id"])
                variables["last_reply"] = inbound.get("text") or ""
                variables["last_reply_choice"] = choice or "fallback"
            elif node["type"] == "wait_reply":
                target = edge_target(outgoing[node_id], "reply")
                variables["last_reply"] = inbound.get("text") or ""
            else:
                raise ValueError("Execution was not waiting on a reply node")
            if not target:
                raise ValueError("Reply node has no matching connection")
            node_id = target
            await self.repository.set_dm_flow_execution_state(
                execution["id"],
                current_node_id=node_id,
                status="running",
                variables=variables,
                event_type="reply_routed",
                details={"target": node_id},
            )
        elif resumed_from:
            node = nodes.get(node_id)
            if not node:
                raise ValueError("Execution references a missing flow node")
            handle = "timeout" if resumed_from == "waiting_reply" else "default"
            target = edge_target(outgoing[node_id], handle)
            if not target:
                status = "expired" if resumed_from == "waiting_reply" else "failed"
                return await self.repository.set_dm_flow_execution_state(
                    execution["id"],
                    status=status,
                    error="Reply timed out" if status == "expired" else "Delay has no next step",
                    event_type=status,
                )
            node_id = target
            await self.repository.set_dm_flow_execution_state(
                execution["id"],
                current_node_id=node_id,
                status="running",
                event_type="execution_resumed",
                details={"target": node_id},
            )

        for _ in range(100):
            node = nodes.get(node_id)
            if not node:
                raise ValueError(f"Flow node {node_id} no longer exists")
            node_type = node["type"]
            config = node.get("config") or {}
            edges = outgoing[node_id]
            if node_type == "start":
                node_id = self._required_target(edges)
            elif node_type in {"reply_router", "wait_reply"}:
                await self._wait_for_reply(execution["id"], node)
                return await self.repository.get_dm_flow_execution(execution["id"])
            elif node_type == "send_text":
                message = render_flow_text(str(config["text"]), variables).strip()
                await self._send_text(execution, message)
                node_id = self._required_target(edges)
            elif node_type == "send_buttons":
                message = render_flow_text(str(config["text"]), variables).strip()
                choices = list(config.get("choices") or [])
                await self._send_buttons(execution, message, choices)
                await self._wait_for_reply(execution["id"], node)
                return await self.repository.get_dm_flow_execution(execution["id"])
            elif node_type == "condition":
                matched = self._condition(config, variables)
                target = edge_target(edges, "true" if matched else "false")
                if not target:
                    raise ValueError("Condition branch is not connected")
                node_id = target
            elif node_type == "delay":
                wake_at = datetime.now(UTC) + timedelta(minutes=int(config["minutes"]))
                return await self.repository.set_dm_flow_execution_state(
                    execution["id"],
                    current_node_id=node_id,
                    status="waiting_delay",
                    variables=variables,
                    wake_at=wake_at,
                    event_type="delay_started",
                    details={"wake_at": wake_at.isoformat()},
                )
            elif node_type == "update_contact":
                value = render_flow_text(str(config["value"]), variables).strip()
                await self.repository.update_contact_from_flow(
                    execution["phone"], str(config["field"]), value
                )
                variables[str(config["field"])] = value
                node_id = self._required_target(edges)
            elif node_type == "handoff":
                conversation = await self._conversation(execution)
                await self.repository.set_takeover(conversation["id"], True)
                return await self.repository.set_dm_flow_execution_state(
                    execution["id"],
                    status="handed_off",
                    variables=variables,
                    event_type="handed_off",
                    details={"reason": str(config.get("reason", "Flow handoff"))},
                )
            elif node_type == "end":
                return await self.repository.set_dm_flow_execution_state(
                    execution["id"],
                    current_node_id=node_id,
                    status="completed",
                    variables=variables,
                    event_type="completed",
                )
            else:
                raise ValueError(f"Unsupported flow node: {node_type}")
            await self.repository.set_dm_flow_execution_state(
                execution["id"],
                current_node_id=node_id,
                status="running",
                variables=variables,
                event_type="node_advanced",
                details={"target": node_id},
            )
        raise ValueError("Flow exceeded the maximum number of immediate steps")

    async def _wait_for_reply(self, execution_id: int, node: dict[str, Any]) -> None:
        timeout = node.get("config", {}).get("timeout_minutes")
        wake_at = datetime.now(UTC) + timedelta(minutes=int(timeout)) if timeout else None
        await self.repository.set_dm_flow_execution_state(
            execution_id,
            current_node_id=str(node["id"]),
            status="waiting_reply",
            wake_at=wake_at,
            event_type="waiting_for_reply",
            details={"wake_at": wake_at.isoformat() if wake_at else None},
        )

    async def _send_text(self, execution: dict[str, Any], message: str) -> None:
        if not message:
            raise ValueError("Rendered flow message is empty")
        conversation = await self._conversation(execution)
        if not await self.repository.within_service_window(conversation["id"]):
            raise ValueError("The WhatsApp service window is closed for this flow message")
        wa_id = await self.waba.send_text(execution["phone"], message)
        if not wa_id:
            raise WABAError("Meta accepted the request without returning a message ID")
        await self.repository.add_message(
            conversation["id"],
            direction="outbound",
            body=message,
            sender="dm_flow",
            wa_message_id=wa_id,
            message_type="text",
            status="accepted",
            metadata={"dm_flow_execution_id": execution["id"]},
        )

    async def _send_buttons(
        self, execution: dict[str, Any], message: str, choices: list[dict[str, Any]]
    ) -> None:
        if not message:
            raise ValueError("Rendered flow button message is empty")
        conversation = await self._conversation(execution)
        if not await self.repository.within_service_window(conversation["id"]):
            raise ValueError("The WhatsApp service window is closed for this button message")
        buttons = [
            {
                "title": str(choice["label"]),
                "payload": f"dmf:{execution['id']}:{choice['key']}",
            }
            for choice in choices
        ]
        wa_id = await self.waba.send_reply_buttons(execution["phone"], message, buttons)
        if not wa_id:
            raise WABAError("Meta accepted the request without returning a message ID")
        await self.repository.add_message(
            conversation["id"],
            direction="outbound",
            body=message,
            sender="dm_flow",
            wa_message_id=wa_id,
            message_type="interactive",
            status="accepted",
            metadata={"dm_flow_execution_id": execution["id"], "buttons": buttons},
        )

    async def _conversation(self, execution: dict[str, Any]) -> dict[str, Any]:
        conversation = None
        if execution.get("conversation_id"):
            conversation = await self.repository.get_conversation(int(execution["conversation_id"]))
        if not conversation:
            conversation = await self.repository.upsert_conversation(execution["phone"])
            await self.repository.bind_dm_flow_conversation(
                execution["id"], conversation["id"]
            )
            execution["conversation_id"] = conversation["id"]
        return conversation

    @staticmethod
    def _condition(config: dict[str, Any], variables: dict[str, Any]) -> bool:
        current: Any = variables
        for part in str(config["field"]).split("."):
            current = current.get(part) if isinstance(current, dict) else None
        operator = str(config["operator"])
        expected = config.get("value")
        if operator == "exists":
            return current is not None and current != ""
        if operator == "equals":
            return str(current or "").casefold() == str(expected or "").casefold()
        if operator == "not_equals":
            return str(current or "").casefold() != str(expected or "").casefold()
        if operator == "contains":
            return str(expected or "").casefold() in str(current or "").casefold()
        return False

    @staticmethod
    def _required_target(edges: list[dict[str, Any]]) -> str:
        target = edge_target(edges)
        if not target:
            raise ValueError("Flow step has no default connection")
        return target

    async def _fail(self, execution: dict[str, Any], error: Exception) -> None:
        LOGGER.exception(
            "dm_flow_execution_failed",
            extra={"event": "dm_flow_execution_failed", "execution_id": execution["id"]},
        )
        await self.repository.set_dm_flow_execution_state(
            execution["id"],
            status="failed",
            error=str(error)[:2000],
            event_type="failed",
            details={"error": str(error)[:2000]},
        )


class DMFlowScheduler:
    def __init__(self, repository: CRMRepository, engine: DMFlowEngine, poll_seconds: int = 5) -> None:
        self.repository = repository
        self.engine = engine
        self.poll_seconds = max(2, poll_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="dm-flow-scheduler")

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
                missing = await self.repository.next_missing_dm_flow_execution()
                if missing:
                    await self.engine.start_for_delivery(
                        missing["delivery_id"], missing["wa_message_id"]
                    )
                    continue
                execution = await self.repository.claim_due_dm_flow_execution()
                if execution:
                    await self.engine.resume_due(execution)
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("dm_flow_scheduler_failed", extra={"event": "dm_flow_scheduler_failed"})
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                pass
