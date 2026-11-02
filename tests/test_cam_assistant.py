from mechman_bot.cam_assistant import respond

BOOKING = "https://crm.mechman.example/book"


def step(state: dict, text: str):
    return respond(state, text, booking_url=BOOKING)


def test_software_pricing_flow_reaches_contextual_booking() -> None:
    result = step({}, "hi")
    result = step(result.state, "1")
    result = step(result.state, "1")
    result = step(result.state, "2")
    result = step(result.state, "3")
    assert result.state["product"] == "PowerMill Ultimate"
    assert BOOKING in result.messages[0]
    assert "interest=Software" in result.messages[0]


def test_post_processor_flow_keeps_machine_and_software_context() -> None:
    result = step({}, "hi")
    for answer in ("1", "2", "2", "1"):
        result = step(result.state, answer)
    assert result.state["product"] == "PowerMill"
    assert result.state["need"] == "4-axis machine"
    assert "book" in result.messages[0].lower()


def test_training_flow_and_explicit_language_switch() -> None:
    result = step({}, "gu")
    assert result.state["language"] == "gu"
    assert "કિંમત" in result.messages[0]
    result = step(result.state, "en")
    assert result.state["language"] == "en"
    assert "Product knowledge" in result.messages[0]


def test_gujarati_navigation_stays_localized_through_booking() -> None:
    result = step({}, "gu")
    result = step(result.state, "1")
    assert "ક્ષેત્ર" in result.messages[0]
    result = step(result.state, "1")
    assert "કામ" in result.messages[0]
    result = step(result.state, "1")
    assert "વિકલ્પ" in result.messages[0]
    result = step(result.state, "1")
    assert "meeting" in result.messages[0]
    assert "MENU" in result.messages[0]


def test_product_knowledge_can_route_to_prices() -> None:
    result = step({}, "hi")
    result = step(result.state, "2")
    result = step(result.state, "2")
    assert "PowerMill" in result.messages[0]
    result = step(result.state, "1")
    assert "₹1,88,000" in result.messages[0]
