from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from mechman_bot.config import Settings
from mechman_bot.database import (
    Campaign,
    CampaignDelivery,
    CampaignRecipient,
    CampaignRun,
    DMFlowExecution,
    DMFlowExecutionEvent,
    MessageTemplate,
)
from mechman_bot.dm_flows import default_graph
from mechman_bot.web import create_app

DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")


async def _seed_accepted_flow_delivery(database, flow_version_id: int) -> tuple[int, str]:
    suffix = uuid4().hex[:12]
    root_message_id = f"wamid.concurrent.{suffix}"
    async with database.session_factory() as session:
        template = MessageTemplate(
            name=f"concurrency_template_{suffix}",
            language="en_US",
            category="MARKETING",
            status="APPROVED",
            body="Reply Yes or No",
        )
        session.add(template)
        await session.flush()
        campaign = Campaign(
            name=f"Concurrency campaign {suffix}",
            template_id=template.id,
            dm_flow_version_id=flow_version_id,
            source_type="paste",
            schedule_type="once",
            scheduled_at=datetime.now(UTC) + timedelta(days=1),
            status="scheduled",
        )
        session.add(campaign)
        await session.flush()
        recipient = CampaignRecipient(
            campaign_id=campaign.id,
            phone="919876540001",
            name="Concurrency Contact",
            variables={"name": "Concurrency Contact"},
            consent_source="security test",
            consent_captured_at=datetime.now(UTC),
            consent_evidence={"reference": "integration-test"},
        )
        session.add(recipient)
        await session.flush()
        run = CampaignRun(
            campaign_id=campaign.id,
            run_number=1,
            scheduled_for=campaign.scheduled_at,
        )
        session.add(run)
        await session.flush()
        delivery = CampaignDelivery(
            run_id=run.id,
            recipient_id=recipient.id,
            status="accepted",
            wa_message_id=root_message_id,
        )
        session.add(delivery)
        await session.commit()
        return delivery.id, root_message_id


async def _start_execution_concurrently(repository, delivery_id: int, root_id: str):
    return await asyncio.gather(
        repository.create_dm_flow_execution(delivery_id, root_id),
        repository.create_dm_flow_execution(delivery_id, root_id),
        repository.create_dm_flow_execution(delivery_id, root_id),
    )


async def _execution_counts(database, delivery_id: int) -> tuple[int, int, int]:
    async with database.session_factory() as session:
        execution = await session.scalar(
            select(DMFlowExecution).where(
                DMFlowExecution.campaign_delivery_id == delivery_id
            )
        )
        execution_count = int(
            await session.scalar(
                select(func.count(DMFlowExecution.id)).where(
                    DMFlowExecution.campaign_delivery_id == delivery_id
                )
            )
            or 0
        )
        started_events = int(
            await session.scalar(
                select(func.count(DMFlowExecutionEvent.id)).where(
                    DMFlowExecutionEvent.execution_id == execution.id,
                    DMFlowExecutionEvent.event_type == "execution_started",
                )
            )
            or 0
        )
        return execution.id, execution_count, started_events


async def _claim_same_inbound_concurrently(
    repository, execution_id: int, inbound_message_id: str
):
    await repository.set_dm_flow_execution_state(
        execution_id,
        current_node_id="reply",
        status="waiting_reply",
        event_type="test_waiting",
    )
    return await asyncio.gather(
        repository.claim_dm_flow_inbound(
            "919876540001",
            inbound_message_id,
            execution_id=execution_id,
            text="Yes",
        ),
        repository.claim_dm_flow_inbound(
            "919876540001",
            inbound_message_id,
            execution_id=execution_id,
            text="Yes",
        ),
    )


@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
def test_dm_flow_api_lifecycle_and_version_conflicts(tmp_path) -> None:
    settings = Settings(
        database_url=DATABASE_URL,
        public_booking_url="https://crm.example.com/book",
        frontend_origin="https://crm.example.com",
        jwt_secret="dm-flow-integration-secret-at-least-32-chars",
        jwt_expire_minutes=720,
        admin_username="dm_flow_admin",
        admin_password="integration-password",
        meeting_duration_minutes=60,
        log_level="INFO",
        meta_access_token="",
        meta_phone_number_id="1395187090344267",
        meta_waba_id="29459993996925480",
        meta_api_version="v26.0",
        meta_webhook_verify_token="verify-token",
        meta_app_secret="app-secret",
        campaign_poll_seconds=5,
        media_root=str(tmp_path / "media"),
    )
    with TestClient(create_app(settings)) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "dm_flow_admin", "password": "integration-password"},
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        invalid_graph = default_graph()
        invalid_graph["edges"].pop()
        invalid = client.post("/api/dm-flows/validate", headers=headers, json=invalid_graph)
        assert invalid.status_code == 422

        created = client.post(
            "/api/dm-flows",
            headers=headers,
            json={
                "name": "Postgres qualification flow",
                "description": "Integration lifecycle coverage",
                "graph": default_graph(),
            },
        )
        assert created.status_code == 201, created.text
        flow = created.json()
        assert flow["draft_version"] == 1

        updated = client.put(
            f"/api/dm-flows/{flow['id']}",
            headers=headers,
            json={
                "name": "Postgres qualification flow v2",
                "description": "Updated draft",
                "graph": default_graph(),
                "expected_version": 1,
            },
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["draft_version"] == 2

        stale = client.put(
            f"/api/dm-flows/{flow['id']}",
            headers=headers,
            json={
                "name": "Stale update",
                "description": "Must fail",
                "graph": default_graph(),
                "expected_version": 1,
            },
        )
        assert stale.status_code == 409

        published = client.post(
            f"/api/dm-flows/{flow['id']}/publish",
            headers=headers,
            json={"expected_version": 2},
        )
        assert published.status_code == 200, published.text
        assert published.json()["version"] == 1

        available = client.get(
            "/api/dm-flows", headers=headers, params={"published_only": True}
        )
        assert available.status_code == 200
        assert any(item["id"] == flow["id"] for item in available.json())

        duplicate = client.post(
            f"/api/dm-flows/{flow['id']}/duplicate", headers=headers
        )
        assert duplicate.status_code == 201, duplicate.text
        copy = duplicate.json()
        assert copy["name"].endswith(" copy")

        archived = client.post(
            f"/api/dm-flows/{copy['id']}/archive",
            headers=headers,
            json={"expected_version": 1},
        )
        assert archived.status_code == 200, archived.text
        assert archived.json()["status"] == "archived"

        listed = client.get("/api/dm-flows", headers=headers)
        assert all(item["id"] != copy["id"] for item in listed.json())


@pytest.mark.skipif(not DATABASE_URL, reason="TEST_DATABASE_URL is not configured")
def test_dm_flow_security_and_concurrency_guards(tmp_path) -> None:
    settings = Settings(
        database_url=DATABASE_URL,
        public_booking_url="https://crm.example.com/book",
        frontend_origin="https://crm.example.com",
        jwt_secret="dm-flow-security-secret-at-least-32-chars",
        jwt_expire_minutes=720,
        admin_username="dm_flow_security_admin",
        admin_password="integration-password",
        meeting_duration_minutes=60,
        log_level="INFO",
        meta_access_token="",
        meta_phone_number_id="1395187090344267",
        meta_waba_id="29459993996925480",
        meta_api_version="v26.0",
        meta_webhook_verify_token="verify-token",
        meta_app_secret="app-secret",
        campaign_poll_seconds=5,
        media_root=str(tmp_path / "media"),
    )
    with TestClient(create_app(settings)) as client:
        login = client.post(
            "/api/auth/login",
            json={
                "username": "dm_flow_security_admin",
                "password": "integration-password",
            },
        )
        assert login.status_code == 200, login.text
        assert login.headers["cache-control"] == "no-store"
        assert login.headers["x-content-type-options"] == "nosniff"
        assert login.headers["x-frame-options"] == "DENY"
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        for method, path, body in (
            ("GET", "/api/dm-flows", None),
            ("POST", "/api/dm-flows/validate", default_graph()),
            ("GET", "/api/dm-flows/executions/1", None),
        ):
            response = client.request(method, path, json=body)
            assert response.status_code == 401
            assert response.json()["detail"] == "Could not validate credentials"
        invalid_token = client.get(
            "/api/dm-flows", headers={"Authorization": "Bearer invalid-token"}
        )
        assert invalid_token.status_code == 401

        disallowed_cors = client.options(
            "/api/dm-flows",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" not in disallowed_cors.headers

        invalid_webhook = client.post(
            "/webhook",
            content=b'{"object":"whatsapp_business_account"}',
            headers={"X-Hub-Signature-256": "sha256=invalid"},
        )
        assert invalid_webhook.status_code == 401

        created = client.post(
            "/api/dm-flows",
            headers=headers,
            json={
                "name": "Security concurrency flow",
                "description": "Security and locking coverage",
                "graph": default_graph(),
            },
        )
        assert created.status_code == 201, created.text
        flow = created.json()
        published = client.post(
            f"/api/dm-flows/{flow['id']}/publish",
            headers=headers,
            json={"expected_version": 1},
        )
        assert published.status_code == 200, published.text

        conflict_copy = client.post(
            f"/api/dm-flows/{flow['id']}/duplicate", headers=headers
        ).json()

        def update_copy(name: str):
            return client.put(
                f"/api/dm-flows/{conflict_copy['id']}",
                headers=headers,
                json={
                    "name": name,
                    "description": "Concurrent update",
                    "graph": default_graph(),
                    "expected_version": 1,
                },
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            update_results = list(
                executor.map(update_copy, ["Concurrent edit A", "Concurrent edit B"])
            )
        assert sorted(response.status_code for response in update_results) == [200, 409]

        database = client.app.state.database
        repository = client.app.state.repository
        delivery_id, root_id = client.portal.call(
            partial(_seed_accepted_flow_delivery, database, published.json()["id"])
        )
        executions = client.portal.call(
            partial(_start_execution_concurrently, repository, delivery_id, root_id)
        )
        assert len({execution["id"] for execution in executions}) == 1
        execution_id, execution_count, started_events = client.portal.call(
            partial(_execution_counts, database, delivery_id)
        )
        assert execution_count == 1
        assert started_events == 1

        inbound_results = client.portal.call(
            partial(
                _claim_same_inbound_concurrently,
                repository,
                execution_id,
                f"{root_id}.inbound",
            )
        )
        assert sum(result is not None for result in inbound_results) == 1
        client.portal.call(
            partial(
                repository.set_dm_flow_execution_state,
                execution_id,
                current_node_id="reply",
                status="waiting_reply",
            )
        )
        cross_phone_claim = client.portal.call(
            partial(
                repository.claim_dm_flow_inbound,
                "919999999999",
                "wamid.inbound.cross-phone",
                execution_id=execution_id,
                text="Yes",
            )
        )
        assert cross_phone_claim is None

        def bad_login(_: int):
            return client.post(
                "/api/auth/login",
                json={
                    "username": "dm_flow_security_admin",
                    "password": "wrong-password",
                },
            )

        with ThreadPoolExecutor(max_workers=10) as executor:
            login_results = list(executor.map(bad_login, range(10)))
        statuses = [response.status_code for response in login_results]
        assert statuses.count(401) == 5
        assert statuses.count(429) == 5
        assert all(
            int(response.headers["retry-after"]) >= 1
            for response in login_results
            if response.status_code == 429
        )
