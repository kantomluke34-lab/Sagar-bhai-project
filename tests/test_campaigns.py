import io
from unittest.mock import AsyncMock

import pytest
from openpyxl import Workbook

from mechman_bot.campaigns import CampaignScheduler, parse_recipient_file, render_parameters
from mechman_bot.dm_flows import default_graph


def test_csv_import_detects_phone_and_preserves_personalization_columns() -> None:
    result = parse_recipient_file(
        "recipients.csv",
        b"Customer Name,Mobile,City\nAsha,+91 98765 43210,Vadodara\nDev,919999999999,Surat\n",
    )
    assert result["phone_column"] == "Mobile"
    assert result["valid_phone_count"] == 2
    assert result["rows"][0]["Customer Name"] == "Asha"


def test_xlsx_import_and_case_insensitive_parameter_mapping() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Phone", "Name", "Product"])
    sheet.append([919876543210, "Asha", "PowerMill"])
    content = io.BytesIO()
    workbook.save(content)

    result = parse_recipient_file("recipients.xlsx", content.getvalue())
    assert result["row_count"] == 1
    assert result["phone_column"] == "Phone"
    assert render_parameters(["name", "PRODUCT"], result["rows"][0]) == [
        "Asha",
        "PowerMill",
    ]


def test_parameter_mapping_rejects_missing_values() -> None:
    with pytest.raises(ValueError, match="Missing value"):
        render_parameters(["name", "city"], {"name": "Asha", "city": ""})


@pytest.mark.asyncio
async def test_campaign_does_not_send_after_consent_is_revoked(tmp_path) -> None:
    repository = AsyncMock()
    repository.campaign_status.return_value = "running"
    repository.contact_opted_in.return_value = False
    waba = AsyncMock()
    scheduler = CampaignScheduler(repository, waba, str(tmp_path))
    await scheduler._deliver({
        "campaign": {"id": 1, "parameter_mapping": [], "throttle_seconds": 0},
        "run": {"id": 2}, "template": {"name": "welcome", "language": "en"},
        "deliveries": [{"delivery_id": 3, "contact_id": 4, "phone": "919876543210", "variables": {}}],
    })
    waba.send_template.assert_not_awaited()
    repository.mark_campaign_delivery.assert_awaited_once_with(3, "failed", error="Contact is no longer opted in")


@pytest.mark.asyncio
async def test_campaign_delivery_starts_its_pinned_flow_execution(tmp_path) -> None:
    repository = AsyncMock()
    repository.get_dm_flow_version.return_value = {"id": 9, "graph": default_graph()}
    repository.campaign_status.return_value = "running"
    repository.contact_opted_in.return_value = True
    waba = AsyncMock()
    waba.send_template.return_value = "wamid.campaign.1"
    flow_engine = AsyncMock()
    scheduler = CampaignScheduler(
        repository,
        waba,
        str(tmp_path),
        dm_flow_engine=flow_engine,
    )
    claimed = {
        "campaign": {
            "id": 1,
            "dm_flow_version_id": 9,
            "parameter_mapping": [],
            "throttle_seconds": 0,
        },
        "run": {"id": 2},
        "template": {
            "name": "campaign_reply",
            "language": "en_US",
            "buttons": [
                {"type": "QUICK_REPLY", "text": "Yes"},
                {"type": "QUICK_REPLY", "text": "No"},
            ],
        },
        "deliveries": [
            {
                "delivery_id": 3,
                "contact_id": 4,
                "phone": "919876543210",
                "variables": {},
            }
        ],
    }

    await scheduler._deliver(claimed)

    assert waba.send_template.await_args.kwargs["quick_reply_payloads"] == [
        "dmf:yes",
        "dmf:no",
    ]
    repository.mark_campaign_delivery.assert_awaited_once_with(
        3,
        "accepted",
        wa_message_id="wamid.campaign.1",
        parameters=[],
    )
    flow_engine.start_for_delivery.assert_awaited_once_with(3, "wamid.campaign.1")
    repository.finish_campaign_run.assert_awaited_once_with(1, 2)


@pytest.mark.asyncio
async def test_campaign_rejects_flow_when_template_reply_labels_do_not_match(tmp_path) -> None:
    repository = AsyncMock()
    repository.get_dm_flow_version.return_value = {"id": 9, "graph": default_graph()}
    waba = AsyncMock()
    scheduler = CampaignScheduler(repository, waba, str(tmp_path))

    await scheduler._deliver(
        {
            "campaign": {"id": 1, "dm_flow_version_id": 9},
            "run": {"id": 2},
            "template": {
                "name": "campaign_reply",
                "language": "en_US",
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Maybe"},
                    {"type": "QUICK_REPLY", "text": "No"},
                ],
            },
            "deliveries": [],
        }
    )

    waba.send_template.assert_not_awaited()
    repository.fail_campaign_run.assert_awaited_once_with(
        1,
        2,
        "Template quick replies no longer match the published DM flow",
    )
