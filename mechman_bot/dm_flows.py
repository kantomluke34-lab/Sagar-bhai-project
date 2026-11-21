"""Validated campaign-specific WhatsApp DM flow contracts and execution helpers."""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

NODE_TYPES = {
    "start",
    "reply_router",
    "wait_reply",
    "send_text",
    "send_buttons",
    "condition",
    "delay",
    "update_contact",
    "handoff",
    "end",
}
TERMINAL_NODE_TYPES = {"handoff", "end"}
CONTACT_FIELDS = {"name", "email", "company", "designation", "city", "lead_stage", "notes"}
CONDITION_OPERATORS = {"equals", "not_equals", "contains", "exists"}
VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.-]+)\s*\}\}")


class FlowPosition(BaseModel):
    x: float = 0
    y: float = 0


class FlowNode(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    type: Literal[
        "start",
        "reply_router",
        "wait_reply",
        "send_text",
        "send_buttons",
        "condition",
        "delay",
        "update_contact",
        "handoff",
        "end",
    ]
    position: FlowPosition = Field(default_factory=FlowPosition)
    config: dict[str, Any] = Field(default_factory=dict)


class FlowEdge(BaseModel):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    source: str = Field(min_length=1, max_length=80)
    target: str = Field(min_length=1, max_length=80)
    source_handle: str = Field(default="default", min_length=1, max_length=80)


class FlowGraph(BaseModel):
    nodes: list[FlowNode] = Field(min_length=2, max_length=100)
    edges: list[FlowEdge] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_graph(self) -> FlowGraph:
        node_ids = [node.id for node in self.nodes]
        edge_ids = [edge.id for edge in self.edges]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("Node IDs must be unique")
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("Edge IDs must be unique")

        nodes = {node.id: node for node in self.nodes}
        starts = [node for node in self.nodes if node.type == "start"]
        ends = [node for node in self.nodes if node.type == "end"]
        if len(starts) != 1:
            raise ValueError("A flow requires exactly one campaign entry")
        if not ends:
            raise ValueError("A flow requires at least one end node")

        outgoing: dict[str, list[FlowEdge]] = {node.id: [] for node in self.nodes}
        incoming: dict[str, list[FlowEdge]] = {node.id: [] for node in self.nodes}
        for edge in self.edges:
            if edge.source not in nodes or edge.target not in nodes:
                raise ValueError(f"Edge {edge.id} references a missing node")
            if edge.source == edge.target:
                raise ValueError(f"Node {edge.source} cannot connect to itself")
            outgoing[edge.source].append(edge)
            incoming[edge.target].append(edge)

        start = starts[0]
        if incoming[start.id]:
            raise ValueError("The campaign entry cannot have incoming connections")
        start_edges = outgoing[start.id]
        if len(start_edges) != 1 or start_edges[0].source_handle != "default":
            raise ValueError("The campaign entry requires one default connection")
        entry_node = nodes[start_edges[0].target]
        if entry_node.type not in {"reply_router", "wait_reply"}:
            raise ValueError("The campaign entry must wait for the recipient's reply")
        for node in self.nodes:
            if node.type in TERMINAL_NODE_TYPES and outgoing[node.id]:
                raise ValueError(f"{node.type.replace('_', ' ').title()} cannot have outgoing connections")
            if node.type not in TERMINAL_NODE_TYPES and not outgoing[node.id]:
                raise ValueError(f"{node.type.replace('_', ' ').title()} needs an outgoing connection")
            self._validate_node(node, outgoing[node.id])

        reachable: set[str] = set()
        pending = deque([start.id])
        while pending:
            current = pending.popleft()
            if current in reachable:
                continue
            reachable.add(current)
            pending.extend(edge.target for edge in outgoing[current])
        missing = set(node_ids) - reachable
        if missing:
            raise ValueError(f"Every node must be reachable; disconnected: {', '.join(sorted(missing))}")

        self._reject_cycles(start.id, outgoing)
        return self

    @staticmethod
    def _validate_node(node: FlowNode, edges: list[FlowEdge]) -> None:
        config = node.config
        handles = [edge.source_handle for edge in edges]
        if len(set(handles)) != len(handles):
            raise ValueError(f"Node {node.id} has duplicate branch connections")
        if node.type in {"start", "send_text", "delay", "update_contact"}:
            if handles != ["default"]:
                raise ValueError(f"Node {node.id} requires one default connection")
        if node.type == "send_text":
            text = str(config.get("text", "")).strip()
            if not 1 <= len(text) <= 4096:
                raise ValueError("Send text nodes require a message of 1-4096 characters")
        elif node.type == "delay":
            minutes = config.get("minutes")
            if not isinstance(minutes, int) or not 1 <= minutes <= 10080:
                raise ValueError("Delay must be between 1 minute and 7 days")
        elif node.type in {"reply_router", "send_buttons"}:
            if node.type == "send_buttons":
                text = str(config.get("text", "")).strip()
                if not 1 <= len(text) <= 1024:
                    raise ValueError("Button messages require 1-1024 characters")
            choices = config.get("choices")
            if not isinstance(choices, list) or not 1 <= len(choices) <= 3:
                raise ValueError("Reply nodes require 1-3 choices")
            keys: set[str] = set()
            aliases: set[str] = set()
            for choice in choices:
                if not isinstance(choice, dict):
                    raise ValueError("Each reply choice must be an object")
                key = str(choice.get("key", "")).strip()
                label = str(choice.get("label", "")).strip()
                if not re.fullmatch(r"[a-zA-Z0-9_-]{1,40}", key):
                    raise ValueError("Reply choice keys may use letters, numbers, underscores, and dashes")
                if key in keys:
                    raise ValueError("Reply choice keys must be unique")
                if not 1 <= len(label) <= 20:
                    raise ValueError("Reply choice labels require 1-20 characters")
                keys.add(key)
                values = choice.get("aliases") or [label]
                if not isinstance(values, list) or not values:
                    raise ValueError(f"Reply choice {label} requires at least one text alias")
                normalized_values = {
                    normalize_reply(value)
                    for value in [label, *(str(value) for value in values)]
                }
                if "" in normalized_values or normalized_values & aliases:
                    raise ValueError("Reply text aliases must be non-empty and unique")
                aliases.update(normalized_values)
            allowed = keys | {"fallback", "timeout"}
            if any(handle not in allowed for handle in handles):
                raise ValueError(f"Node {node.id} has an unknown reply branch")
            if not keys.issubset(set(handles)):
                raise ValueError(f"Node {node.id} needs a connection for every reply choice")
            FlowGraph._validate_timeout(config, handles)
        elif node.type == "wait_reply":
            if "reply" not in handles:
                raise ValueError("Wait for reply needs a reply connection")
            if any(handle not in {"reply", "timeout"} for handle in handles):
                raise ValueError("Wait for reply only supports reply and timeout branches")
            FlowGraph._validate_timeout(config, handles)
        elif node.type == "condition":
            field = str(config.get("field", "")).strip()
            operator = str(config.get("operator", ""))
            if not field:
                raise ValueError("Condition nodes require a variable")
            if operator not in CONDITION_OPERATORS:
                raise ValueError("Condition nodes require a supported operator")
            if set(handles) != {"true", "false"}:
                raise ValueError("Condition nodes require true and false connections")
        elif node.type == "update_contact":
            field = str(config.get("field", ""))
            if field not in CONTACT_FIELDS:
                raise ValueError("Update contact uses an unsupported field")
            if not str(config.get("value", "")).strip():
                raise ValueError("Update contact requires a value")

    @staticmethod
    def _validate_timeout(config: dict[str, Any], handles: list[str]) -> None:
        timeout = config.get("timeout_minutes")
        if timeout is None:
            if "timeout" in handles:
                raise ValueError("A timeout branch requires timeout minutes")
            return
        if not isinstance(timeout, int) or not 1 <= timeout <= 10080:
            raise ValueError("Reply timeout must be between 1 minute and 7 days")
        if "timeout" not in handles:
            raise ValueError("Reply timeout requires a timeout connection")

    @staticmethod
    def _reject_cycles(start_id: str, outgoing: dict[str, list[FlowEdge]]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("Flow cycles are not supported in this release")
            if node_id in visited:
                return
            visiting.add(node_id)
            for edge in outgoing[node_id]:
                visit(edge.target)
            visiting.remove(node_id)
            visited.add(node_id)

        visit(start_id)


class DMFlowCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=1000)
    graph: FlowGraph


class DMFlowUpdate(DMFlowCreate):
    expected_version: int = Field(ge=1)


class DMFlowCommand(BaseModel):
    expected_version: int = Field(ge=1)


def normalize_reply(value: str) -> str:
    """Normalize human replies without making broad fuzzy matches."""
    value = value.casefold().strip()
    value = re.sub(r"^[\s\W_]+|[\s\W_]+$", "", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value)


def graph_checksum(graph: dict[str, Any]) -> str:
    canonical = json.dumps(graph, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def graph_indexes(graph: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    nodes = {str(node["id"]): node for node in graph["nodes"]}
    outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes}
    for edge in graph["edges"]:
        outgoing[str(edge["source"])].append(edge)
    return nodes, outgoing


def edge_target(edges: list[dict[str, Any]], handle: str = "default") -> str | None:
    for edge in edges:
        if str(edge.get("source_handle", "default")) == handle:
            return str(edge["target"])
    return None


def campaign_entry_choices(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Return reply choices that directly follow the campaign entry."""
    nodes, outgoing = graph_indexes(graph)
    start = next((node for node in nodes.values() if node["type"] == "start"), None)
    if not start:
        return []
    target = edge_target(outgoing[start["id"]])
    node = nodes.get(target or "")
    if not node or node["type"] != "reply_router":
        return []
    return list(node.get("config", {}).get("choices") or [])


def render_flow_text(template: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        current: Any = variables
        for part in match.group(1).split("."):
            if not isinstance(current, dict) or part not in current:
                return ""
            current = current[part]
        return str(current if current is not None else "")

    return VARIABLE_PATTERN.sub(replace, template)


def choice_for_reply(node: dict[str, Any], text: str, payload: str | None) -> str | None:
    choices = node.get("config", {}).get("choices") or []
    if payload:
        payload_key = payload.rsplit(":", 1)[-1]
        if any(str(choice.get("key")) == payload_key for choice in choices):
            return payload_key
    normalized = normalize_reply(text)
    for choice in choices:
        aliases = [choice.get("label", ""), *(choice.get("aliases") or [])]
        if normalized in {normalize_reply(str(alias)) for alias in aliases}:
            return str(choice["key"])
    return None


def default_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 80, "y": 80}, "config": {}},
            {
                "id": "reply",
                "type": "reply_router",
                "position": {"x": 80, "y": 240},
                "config": {
                    "choices": [
                        {"key": "yes", "label": "Yes", "aliases": ["yes", "y"]},
                        {"key": "no", "label": "No", "aliases": ["no", "n"]},
                    ]
                },
            },
            {"id": "yes_end", "type": "end", "position": {"x": -40, "y": 430}, "config": {}},
            {"id": "no_end", "type": "end", "position": {"x": 210, "y": 430}, "config": {}},
        ],
        "edges": [
            {"id": "start_reply", "source": "start", "target": "reply", "source_handle": "default"},
            {"id": "reply_yes", "source": "reply", "target": "yes_end", "source_handle": "yes"},
            {"id": "reply_no", "source": "reply", "target": "no_end", "source_handle": "no"},
        ],
    }
