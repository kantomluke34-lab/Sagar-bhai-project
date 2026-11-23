# Mechman CRM — Client Handoff

## Delivered

The latest release is committed and available on the project’s `main` branch.

- Commit: `162d0e2` — **Harden campaign lifecycle and messaging UX**
- Repository: [Sagar-bhai-project](https://github.com/kantomluke34-lab/Sagar-bhai-project)

This release improves the campaign, DM-flow, template, and WhatsApp messaging experience.

## What you can now do

### Campaigns

- Create campaigns with protection against accidental duplicate submissions.
- Choose a campaign-specific DM flow for replies.
- Open a campaign to review delivery results and failure reasons.
- Pause, resume, cancel, retry failed messages, or archive completed campaigns.
- Confirm an archive action by entering the campaign name, helping prevent accidental deletion.

### DM flows

- Set up a DM flow directly while creating or editing a campaign.
- Published flows are available for selection in the campaign window.
- A campaign’s selected flow handles its replies before the general assistant flow.
- The DM-flow editor now groups actions more clearly and uses consistent spacing.

### Message templates

- Create and edit WhatsApp templates with clearer guidance.
- Add up to three quick-reply buttons.
- Enter examples for message variables such as `{{1}}` and `{{2}}`.
- See whether a template is pending, approved, rejected, or needs recovery after a connection interruption.

### WhatsApp reliability

- Delivery failures now show more useful reasons.
- The system pauses new sends when WhatsApp reports a temporary sending limit, rather than repeatedly retrying and worsening the limit.
- Campaign, DM-flow, notification, and bot sends use the same safety protection.
- WhatsApp connection health is visible from the application settings.

## How to use the main workflow

1. Add contacts and confirm that each person has agreed to receive WhatsApp messages.
2. Create or select an approved WhatsApp template.
3. Open **Campaigns** and choose an audience.
4. Choose the approved template and send time.
5. Optionally select **Setup DM Flow** and choose the flow that should handle replies.
6. Schedule the campaign and open it later to review delivery results.

Only approved templates and opted-in contacts should be used for campaigns.

## WhatsApp account status observed during verification

- WABA status: **Active**
- Phone status: **Connected**
- Verified business name: **Approved**
- Phone quality: **Green**
- Messaging tier: **TIER_2K**

`TIER_2K` represents up to 2,000 unique recipients outside the WhatsApp service window during the applicable rolling period. WhatsApp may still apply a short-term throughput limit; the application now detects that condition and pauses sending safely.

## Release verification

Before delivery, the team verified:

- 52 backend tests passed.
- 20 frontend tests passed.
- The frontend production build passed.
- Code quality checks passed.
- No production frontend dependency vulnerabilities were reported by `npm audit --omit=dev`.

## Before going live

The release still needs to be pulled onto the Contabo production server and followed by a short production smoke test:

- sign in;
- create one test campaign;
- select a published DM flow;
- send to one approved test contact;
- confirm the delivery result and reply routing;
- confirm the WhatsApp status page is healthy.

The production deployment procedure is documented in [DEPLOYMENT_CONTABO.md](./DEPLOYMENT_CONTABO.md). The general day-to-day product guide is [CLIENT_HANDOFF_GUIDE.md](./CLIENT_HANDOFF_GUIDE.md).

## Support notes

If a campaign shows a temporary WhatsApp sending-limit error, wait for the limit to clear before retrying. Do not repeatedly reschedule the same campaign during the limit window. For a permanent delivery failure, open the campaign delivery log and review the recipient and error reason before retrying.
