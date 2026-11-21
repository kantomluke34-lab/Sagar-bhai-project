from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from mechman_bot.dm_flow_engine import DMFlowEngine
from mechman_bot.dm_flows import (
    FlowGraph,
    choice_for_reply,
    default_graph,
    render_flow_text,
)


def test_default_campaign_flow_is_valid() -> None:
    graph = FlowGraph.model_validate(default_graph())

    assert graph.nodes[0].type == "start"
    assert {edge.source_handle for edge in graph.edges if edge.source == "reply"} == {
        "yes",
        "no",
    }


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda graph: graph["edges"].pop(),
            "connection for every reply choice",
        ),
        (
            lambda graph: graph["edges"].append(
                {
                    "id": "cycle",
                    "source": "yes_end",
                    "target": "reply",
                    "source_handle": "default",
                }
            ),
            "cannot have outgoing connections",
        ),
        (
            lambda graph: graph["edges"][0].update(target="yes_end"),
            "must wait for the recipient's reply",
        ),
    ],
)
def test_invalid_flow_shapes_are_rejected(mutate: Any, message: str) -> None:
    graph = default_graph()
    mutate(graph)

    with pytest.raises(ValidationError, match=message):
        FlowGraph.model_validate(graph)


def test_reply_matching_accepts_button_payload_label_and_alias() -> None:
    reply_node = default_graph()["nodes"][1]

    assert choice_for_reply(reply_node, "", "dmf:42:yes") == "yes"
    assert choice_for_reply(reply_node, "Yes!", None) == "yes"
    assert choice_for_reply(reply_node, "N", None) == "no"
    assert choice_for_reply(reply_node, "maybe", None) is None


def test_flow_text_renders_known_variables_and_blanks_missing_values() -> None:
    assert (
        render_flow_text(
            "Hi {{name}}, campaign {{campaign.id}} {{missing}}",
            {"name": "Asha", "campaign": {"id": 17}},
        )
        == "Hi Asha, campaign 17 "
    )


class FlowRepositoryStub:
    def __init__(self) -> None:
        self.execution: dict[str, Any] = {
            "id": 41,
            "current_node_id": "start",
            "status": "processing_start",
            "variables": {"name": "Asha"},
            "graph": default_graph(),
            "phone": "919876543210",
            "conversation_id": None,
        }
        self.events: list[dict[str, Any]] = []

    async def set_dm_flow_execution_state(self, execution_id: int, **changes: Any) -> dict[str, Any]:
        assert execution_id == self.execution["id"]
        for key in ("current_node_id", "status", "variables", "wake_at", "error"):
            if key in changes:
                self.execution[key] = changes[key]
        if changes.get("event_type"):
            self.events.append(
                {
                    "event_type": changes["event_type"],
                    "details": changes.get("details") or {},
                }
            )
        return deepcopy(self.execution)

    async def get_dm_flow_execution(self, execution_id: int) -> dict[str, Any]:
        assert execution_id == self.execution["id"]
        return deepcopy(self.execution)

    async def add_dm_flow_execution_event(
        self, execution_id: int, event_type: str, **values: Any
    ) -> None:
        assert execution_id == self.execution["id"]
        self.events.append({"event_type": event_type, **values})


@pytest.mark.asyncio
async def test_campaign_reply_happy_path_completes_pinned_flow() -> None:
    repository = FlowRepositoryStub()
    engine = DMFlowEngine(repository, object())  # type: ignore[arg-type]

    waiting = await engine._advance(deepcopy(repository.execution))
    assert waiting is not None
    assert waiting["status"] == "waiting_reply"
    assert waiting["current_node_id"] == "reply"

    completed = await engine._advance(
        deepcopy(repository.execution),
        inbound={"text": "Yes", "payload": None},
    )
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["current_node_id"] == "yes_end"
    assert completed["variables"]["last_reply_choice"] == "yes"


@pytest.mark.asyncio
async def test_unmatched_reply_stays_with_campaign_flow() -> None:
    repository = FlowRepositoryStub()
    repository.execution.update(current_node_id="reply", status="waiting_reply")
    engine = DMFlowEngine(repository, object())  # type: ignore[arg-type]

    waiting = await engine._advance(
        deepcopy(repository.execution),
        inbound={"text": "Maybe later", "payload": None},
    )

    assert waiting is not None
    assert waiting["status"] == "waiting_reply"
    assert any(event["event_type"] == "reply_unmatched" for event in repository.events)
