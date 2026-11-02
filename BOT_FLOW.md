# Mechman CAM Assistant flow

The WhatsApp assistant is deterministic and follows the supplied `Mechman CAM Assistant.html` decision tree. It does not call an LLM. The HTML is a product/design reference only; it is not executed in production.

## Controls

- `EN` and `GU` switch language and restart the menu.
- `MENU`, `M`, `START`, `RESTART`, `HI`, and `HELLO` return to the main menu.
- `BOOK`, `MEETING`, `DEMO`, `QUOTATION`, and `QUOTE` return the contextual internal-booking link.
- While an admin has selected **Take Over**, inbound messages are recorded but no bot reply is sent.
- Only an explicit **Return to Bot** action resumes automation. Returning does not generate an unsolicited message; the next inbound customer message continues the saved flow.

## Decision tree

```text
Welcome
  |
  +-- 1 Pricing
  |     |
  |     +-- 1 Software
  |     |     +-- 3-axis CAM
  |     |     +-- 4/5-axis CAM
  |     |     +-- Design (CAD)
  |     |            -> option and price -> contextual meeting link
  |     |
  |     +-- 2 Post Processor
  |     |     +-- Fusion / PowerMill
  |     |            -> machine type and price -> contextual meeting link
  |     |
  |     +-- 3 Training
  |           +-- Fusion / PowerMill
  |                  -> course -> online / Vadodara -> meeting link
  |
  +-- 2 Product Knowledge
        +-- Fusion
        +-- PowerMill
        +-- FeatureCAM
        +-- Post Processor
        +-- Training
               -> overview -> price or demo -> meeting link
```

## Internal booking hand-off

The bot never confirms a slot inside WhatsApp. It sends `PUBLIC_BOOKING_URL` with URL-encoded `interest` and `purpose` fields. The internal form then:

1. collects name, phone, email, date and time;
2. checks Mechman's Monday-Saturday, 9:00 AM-6:30 PM IST calendar;
3. rejects occupied or past slots;
4. creates the contact, conversation and meeting in PostgreSQL;
5. shows the booking reference to the customer.

The single admin confirms, reschedules, completes, cancels, or marks the meeting no-show in the CRM.

## Messaging compliance

- Free-form admin and automated text is allowed only within 24 hours of the latest inbound customer message.
- Business-initiated reminders and follow-ups outside that window require an approved Meta template.
- Draft, pending, paused, disabled, or rejected templates cannot be sent.
- Every inbound and outbound WhatsApp message is logged with its WAMID and delivery status where available.

## Source-of-truth files

- Conversation state and copy: `mechman_bot/cam_assistant.py`
- Webhook and takeover enforcement: `mechman_bot/webhook.py`
- Reminder/follow-up compliance: `mechman_bot/notifications.py`
- Calendar and public booking API: `mechman_bot/api.py`
