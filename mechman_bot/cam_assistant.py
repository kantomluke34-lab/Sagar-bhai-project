"""Bilingual deterministic bot based on the approved Mechman CAM Assistant flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

CATALOG = {
    "3axis": [
        ("Fusion Cloud Commercial", "₹43,000 + GST", "CAD + 3-axis CAM + turning"),
        ("PowerMill Standard", "₹1,88,000 + GST", "3-axis, 3+2 and high-speed machining"),
        ("FeatureCAM Ultimate", "₹2,44,000 + GST", "Feature-based milling and turning"),
    ],
    "5axis": [
        (
            "Fusion for Manufacturing",
            "₹1,29,000 + GST",
            "3/4/5-axis and turn-mill; post from ₹75,000",
        ),
        ("FeatureCAM Ultimate", "₹2,44,000 + GST", "4/5-axis and mill-turn; post from ₹75,000"),
        ("PowerMill Ultimate", "₹2,85,000 + GST", "Simultaneous 5-axis; post from ₹75,000"),
    ],
    "design": [
        ("Fusion", "₹43,000 + GST", "3D CAD, assemblies, drawings and surfacing"),
        ("PowerShape", "₹1,01,000 + GST", "Mold and die design with hybrid modeling"),
        ("AutoCAD LT", "Price on request", "2D drafting"),
        ("AutoCAD with toolsets", "Price on request", "3D work and industry toolsets"),
    ],
}

POST_PRICES = [
    ("4-axis machine", "₹75,000 + GST"),
    ("5-axis machine", "₹85,000 + GST"),
    ("3+2 / 4+1 rotary", "₹75,000 + GST"),
]

TRAINING = {
    "fusion": [
        ("Fusion Full CAD", "₹15,000", "20 days · 2 hrs/day"),
        ("Fusion CAD + 3-axis CAM", "₹20,000", "25 days · 2 hrs/day"),
        ("Fusion CAD + 3, 4 & 5-axis CAM", "₹25,000", "35 days · 2 hrs/day"),
    ],
    "powermill": [
        ("PowerMill 3-axis CAM", "₹18,000", "20 days · 2 hrs/day"),
        ("PowerMill 3, 4 & 5-axis CAM", "₹25,000", "35 days · 2 hrs/day"),
    ],
}

KNOWLEDGE = {
    "fusion": (
        "Autodesk Fusion is a cloud-based CAD, CAM and CAE platform that takes work from design to manufacturing. "
        "Fusion covers product design, drawings, collaboration, turning and regular 3-axis machining. Fusion for "
        "Manufacturing adds advanced 4/5-axis machining, probing, nesting and manufacturing automation."
    ),
    "powermill": (
        "Autodesk PowerMill is advanced CAM software for complex CNC components. Standard is suited to high-speed "
        "3-axis and positional 3+2 work. Ultimate adds simultaneous 4/5-axis machining, advanced collision avoidance, "
        "blade/impeller/port strategies, robot programming and specialized manufacturing workflows."
    ),
    "featurecam": (
        "Autodesk FeatureCAM uses automatic feature recognition and knowledge-based machining to program production "
        "parts quickly. It supports milling, turning, turn-mill, Swiss-type machining, wire EDM and machine simulation."
    ),
    "post": (
        "Mechman builds and modifies post processors for Fanuc, Siemens, Heidenhain, Syntec and Mitsubishi controllers. "
        "Posts are configured for the exact machine kinematics, tested, and supplied with prove-out support."
    ),
}


@dataclass(frozen=True)
class BotReply:
    state: dict[str, Any]
    messages: tuple[str, ...]


def _choice(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _numbered(items: list[tuple[str, ...]]) -> str:
    return "\n\n".join(
        f"{index}. {item[0]}\n{item[1]}\n{' · '.join(item[2:])}".strip()
        for index, item in enumerate(items, 1)
    )


def _text(language: str, english: str, gujarati: str) -> str:
    return gujarati if language == "gu" else english


def _welcome(language: str) -> str:
    if language == "gu":
        return (
            "નમસ્તે! Mechman Solutionsમાં આપનું સ્વાગત છે 👋\n"
            "અમે Autodesk CAD/CAM software, post processors અને trainingમાં મદદ કરીએ છીએ.\n\n"
            "1 - 💰 કિંમત\n2 - 📘 Product માહિતી\n\nEnglish માટે EN લખો."
        )
    return (
        "Hi! Welcome to Mechman Solutions 👋\n"
        "We help manufacturers with Autodesk CAD/CAM software, post processors and training.\n\n"
        "1 - 💰 Pricing\n2 - 📘 Product knowledge\n\nગુજરાતી માટે GU લખો."
    )


def _finish(state: dict[str, Any], booking_url: str) -> str:
    params = {
        "interest": str(state.get("area") or state.get("product") or "CAM software"),
        "purpose": " · ".join(
            str(value)
            for value in (state.get("product"), state.get("need"), state.get("mode"))
            if value
        ),
    }
    link = f"{booking_url}?{urlencode(params)}"
    return _text(
        str(state.get("language", "en")),
        "Want a quotation or a free demo? Book a convenient meeting with the Mechman team:\n\n"
        f"{link}\n\nReply MENU to explore another option.",
        "Quotation અથવા free demo જોઈએ છે? Mechman ટીમ સાથે અનુકૂળ meeting બુક કરો:\n\n"
        f"{link}\n\nબીજો વિકલ્પ જોવા MENU લખો.",
    )


def respond(
    current_state: dict[str, Any] | None,
    text: str,
    *,
    booking_url: str,
    display_name: str = "",
) -> BotReply:
    state = dict(current_state or {})
    state.setdefault("stage", "welcome")
    state.setdefault("language", "en")
    normalized = _choice(text)

    if normalized in {"gu", "ગુજરાતી", "gujarati"}:
        state = {"stage": "welcome", "language": "gu"}
        return BotReply(state, (_welcome("gu"),))
    if normalized in {"en", "english"}:
        state = {"stage": "welcome", "language": "en"}
        return BotReply(state, (_welcome("en"),))
    if normalized in {"hi", "hello", "hey", "start", "restart", "menu", "m", "નમસ્તે"}:
        language = state.get("language", "en")
        state = {"stage": "welcome", "language": language}
        return BotReply(state, (_welcome(language),))
    if normalized in {"book", "meeting", "demo", "quotation", "quote"}:
        return BotReply(state, (_finish(state, booking_url),))

    stage = state["stage"]
    language = state["language"]

    if stage == "welcome":
        if normalized in {"1", "pricing", "price", "કિંમત"}:
            state.update(stage="pricing_area", interest="Pricing")
            message = _text(
                language,
                "Which area are you interested in?\n\n1 - Software\n2 - Post Processor\n3 - Training",
                "તમને કયા ક્ષેત્રમાં રસ છે?\n\n1 - Software\n2 - Post Processor\n3 - Training",
            )
        elif normalized in {"2", "knowledge", "product knowledge", "માહિતી"}:
            state.update(stage="knowledge", interest="Knowledge")
            message = _text(
                language,
                "Which topic would you like to know about?\n\n1 - Fusion\n2 - PowerMill\n3 - FeatureCAM\n4 - Post Processor\n5 - Training",
                "તમે કયા વિષય વિશે જાણવા માંગો છો?\n\n1 - Fusion\n2 - PowerMill\n3 - FeatureCAM\n4 - Post Processor\n5 - Training",
            )
        else:
            message = _welcome(language)
        return BotReply(state, (message,))

    if stage == "pricing_area":
        if normalized in {"1", "software"}:
            state.update(stage="software_need", area="Software")
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "What kind of work do you need the software for?\n\n1 - 3-axis CAM\n2 - 4 / 5-axis CAM\n3 - Design (CAD)",
                        "તમારે software કયા કામ માટે જોઈએ છે?\n\n1 - 3-axis CAM\n2 - 4 / 5-axis CAM\n3 - Design (CAD)",
                    ),
                ),
            )
        if normalized in {"2", "post", "post processor"}:
            state.update(stage="post_software", area="Post Processor")
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "We build tested posts for Fanuc, Siemens, Heidenhain, Syntec and Mitsubishi controllers.\n\nWhich software do you use?\n1 - Fusion\n2 - PowerMill",
                        "અમે Fanuc, Siemens, Heidenhain, Syntec અને Mitsubishi controller માટે tested post બનાવીએ છીએ.\n\nતમે કયું software વાપરો છો?\n1 - Fusion\n2 - PowerMill",
                    ),
                ),
            )
        if normalized in {"3", "training"}:
            state.update(stage="training_software", area="Training")
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "Mechman is an Autodesk Authorized Training Center.\n\nWhich software do you want to learn?\n1 - Fusion\n2 - PowerMill",
                        "Mechman Autodesk Authorized Training Center છે.\n\nતમે કયું software શીખવા માંગો છો?\n1 - Fusion\n2 - PowerMill",
                    ),
                ),
            )
        return BotReply(
            state,
            (
                _text(
                    language,
                    "Please choose 1 for Software, 2 for Post Processor, or 3 for Training.",
                    "Software માટે 1, Post Processor માટે 2 અથવા Training માટે 3 પસંદ કરો.",
                ),
            ),
        )

    if stage == "software_need":
        keys = {
            "1": "3axis",
            "3-axis cam": "3axis",
            "2": "5axis",
            "4 / 5-axis cam": "5axis",
            "4/5-axis cam": "5axis",
            "3": "design",
            "design": "design",
            "design (cad)": "design",
        }
        key = keys.get(normalized)
        if not key:
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "Please choose 1 for 3-axis CAM, 2 for 4/5-axis CAM, or 3 for Design.",
                        "3-axis CAM માટે 1, 4/5-axis CAM માટે 2 અથવા Design માટે 3 પસંદ કરો.",
                    ),
                ),
            )
        state.update(stage="software_select", need=key)
        return BotReply(
            state,
            (
                _text(
                    language,
                    f"Here are the options:\n\n{_numbered(CATALOG[key])}\n\nReply with the option number.",
                    f"આ વિકલ્પો ઉપલબ્ધ છે:\n\n{_numbered(CATALOG[key])}\n\nવિકલ્પનો નંબર લખો.",
                ),
            ),
        )

    if stage == "software_select":
        items = CATALOG.get(str(state.get("need")), [])
        try:
            selected = items[int(normalized) - 1]
        except (ValueError, IndexError):
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "Please reply with one of the displayed option numbers.",
                        "દર્શાવેલા વિકલ્પોમાંથી એક નંબર લખો.",
                    ),
                ),
            )
        state.update(stage="finished", product=selected[0])
        return BotReply(state, (_finish(state, booking_url),))

    if stage == "post_software":
        product = {
            "1": "Fusion",
            "fusion": "Fusion",
            "2": "PowerMill",
            "powermill": "PowerMill",
        }.get(normalized)
        if not product:
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "Please choose 1 for Fusion or 2 for PowerMill.",
                        "Fusion માટે 1 અથવા PowerMill માટે 2 પસંદ કરો.",
                    ),
                ),
            )
        state.update(stage="post_machine", product=product)
        return BotReply(
            state,
            (
                _text(
                    language,
                    f"{product} post processor prices:\n\n{_numbered(POST_PRICES)}\n\nWhich machine type do you have? Reply with the option number.",
                    f"{product} post processorની કિંમત:\n\n{_numbered(POST_PRICES)}\n\nતમારી પાસે કયા પ્રકારનું machine છે? વિકલ્પનો નંબર લખો.",
                ),
            ),
        )

    if stage == "post_machine":
        try:
            selected = POST_PRICES[int(normalized) - 1]
        except (ValueError, IndexError):
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "Please reply with machine option 1, 2, or 3.",
                        "Machine માટે વિકલ્પ 1, 2 અથવા 3 લખો.",
                    ),
                ),
            )
        state.update(stage="finished", need=selected[0])
        return BotReply(state, (_finish(state, booking_url),))

    if stage == "training_software":
        product = {
            "1": "fusion",
            "fusion": "fusion",
            "2": "powermill",
            "powermill": "powermill",
        }.get(normalized)
        if not product:
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "Please choose 1 for Fusion or 2 for PowerMill.",
                        "Fusion માટે 1 અથવા PowerMill માટે 2 પસંદ કરો.",
                    ),
                ),
            )
        state.update(stage="training_course", product=product)
        return BotReply(
            state,
            (
                _text(
                    language,
                    f"Available courses:\n\n{_numbered(TRAINING[product])}\n\nReply with the course number.",
                    f"ઉપલબ્ધ courses:\n\n{_numbered(TRAINING[product])}\n\nCourseનો નંબર લખો.",
                ),
            ),
        )

    if stage == "training_course":
        courses = TRAINING.get(str(state.get("product")), [])
        try:
            selected = courses[int(normalized) - 1]
        except (ValueError, IndexError):
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "Please reply with one of the displayed course numbers.",
                        "દર્શાવેલા courseમાંથી એક નંબર લખો.",
                    ),
                ),
            )
        state.update(stage="training_mode", need=selected[0])
        return BotReply(
            state,
            (
                _text(
                    language,
                    "How would you like to attend?\n\n1 - Online\n2 - Vadodara training center",
                    "તમે training કેવી રીતે લેવા માંગો છો?\n\n1 - Online\n2 - Vadodara training center",
                ),
            ),
        )

    if stage == "training_mode":
        mode = {
            "1": "Online",
            "online": "Online",
            "2": "Vadodara training center",
            "center": "Vadodara training center",
        }.get(normalized)
        if not mode:
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "Please choose 1 for Online or 2 for the Vadodara training center.",
                        "Online માટે 1 અથવા Vadodara training center માટે 2 પસંદ કરો.",
                    ),
                ),
            )
        state.update(stage="finished", mode=mode)
        return BotReply(state, (_finish(state, booking_url),))

    if stage == "knowledge":
        key = {
            "1": "fusion",
            "fusion": "fusion",
            "2": "powermill",
            "powermill": "powermill",
            "3": "featurecam",
            "featurecam": "featurecam",
            "4": "post",
            "post": "post",
            "post processor": "post",
            "5": "training",
            "training": "training",
        }.get(normalized)
        if not key:
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "Please choose a topic from 1 to 5.",
                        "1 થી 5માંથી કોઈ વિષય પસંદ કરો.",
                    ),
                ),
            )
        if key == "training":
            state.update(stage="training_software", area="Training")
            return BotReply(
                state,
                (
                    _text(
                        language,
                        "All courses run online or at our Vadodara training center, 2 hours a day.\n\n1 - Fusion\n2 - PowerMill",
                        "બધા courses online અથવા Vadodara training center પર દરરોજ 2 કલાક ચાલે છે.\n\n1 - Fusion\n2 - PowerMill",
                    ),
                ),
            )
        state.update(stage="knowledge_action", area=key)
        return BotReply(
            state,
            (
                f"{KNOWLEDGE[key]}\n\n"
                + _text(
                    language, "1 - See prices\n2 - Book a demo", "1 - કિંમત જુઓ\n2 - Demo બુક કરો"
                ),
            ),
        )

    if stage == "knowledge_action":
        if normalized in {"2", "book", "demo"}:
            return BotReply(state, (_finish(state, booking_url),))
        if normalized in {"1", "price", "prices"}:
            area = state.get("area")
            if area == "post":
                message = _numbered(POST_PRICES)
            elif area == "powermill":
                message = _numbered([CATALOG["3axis"][1], CATALOG["5axis"][2]])
            elif area == "featurecam":
                message = _numbered([CATALOG["5axis"][1]])
            else:
                message = _numbered([CATALOG["3axis"][0], CATALOG["5axis"][0]])
            state["stage"] = "finished"
            return BotReply(state, (f"{message}\n\n{_finish(state, booking_url)}",))
        return BotReply(
            state,
            (
                _text(
                    language,
                    "Reply 1 to see prices or 2 to book a demo.",
                    "કિંમત જોવા 1 અથવા demo બુક કરવા 2 લખો.",
                ),
            ),
        )

    return BotReply(state, (_finish(state, booking_url),))
