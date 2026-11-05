# Mechman: quick client guide

Use the left menu to change pages. **Sign in** to start; **Sign out** when finished.

## Send a WhatsApp broadcast

```text
CRM Contacts       Templates          Campaigns
Add people    -->  Get a message -->  Choose audience
Record their       approved by Meta    + message + time
permission                             --> Schedule --> Check delivery
```

**Audience = who receives it. Campaign = what they receive and when.** Saving an audience sends nothing.

### 1. Add people and permission

**CRM Contacts** → **Add contact** for one person, or **Import** for a spreadsheet. Open a person, set **WhatsApp consent** to **Opted in** only if they agreed, record where and when they agreed, then **Save consent**. Without this, they cannot receive a campaign from your contact list.

### 2. Get a message approved

```text
Templates --> New template --> Write message --> Save template
          --> Submit for review --> Sync with Meta --> Approved
```

Use `{{1}}`, `{{2}}` for details that change by person:

```text
Message:  Hello {{1}}, your meeting is on {{2}}.
Examples: Asha, Tuesday at 3 pm
```

Enter one example per number, in order, under **Variable examples**. **Pending** means Meta is reviewing it. If **Rejected**, read the reason, **Edit**, save, and submit again. **Duplicate** makes a fresh draft from an approved or pending message. Only **Approved** messages can be used in campaigns.

### 3. Choose people and schedule

```text
Campaigns --> New audience --> Choose opted-in contacts
          --> Save audience
          --> New campaign --> Approved message + recipients + time
          --> Schedule campaign --> Open campaign to check results
```

Tick the people you want and select **Save audience** or **Save & create campaign** to continue directly. Only contacts marked **Opted in** appear. **Edit** changes an audience; **X** deletes it. A campaign already scheduled keeps its original recipients.

In **New campaign**, choose recipients from a **Saved audience**, a **CSV / Excel** spreadsheet, or **Paste numbers**. For a spreadsheet, match its phone and name columns. For a spreadsheet or pasted numbers, confirm that everyone agreed to WhatsApp messages and enter where and when. Match each `{{1}}`, `{{2}}` to a contact detail or spreadsheet column.

Choose **Once**, **Daily**, or **Weekly** and a future time in India time. **Sending pace** controls the gap between messages; **Meta managed** lets Meta choose. Select **Schedule campaign** and check the confirmation.

```text
Scheduled --> Accepted --> Delivered --> Read
                         \-> Failed --> Review --> Retry failed only
```

Open a campaign to see results. **Copy** or **Export CSV** saves the delivery list. **Pause**, **Resume**, and **Cancel** control further sending. Review failures before **Retry failed only**, which attempts those numbers again.

## Other everyday tasks

| Page | What to use |
| --- | --- |
| **Dashboard** | See contact and meeting totals. Pie chart = meetings by current status. Monthly chart = new meeting requests. |
| **CRM Contacts** | **Search**, **Add contact**, **Import**, **Export CSV**. Open a row to **Edit contact**, **Mark lead complete** or **Reopen lead**, and save WhatsApp permission. **Previous / Next** changes page. |
| **Meetings** | **Search** or filter by status. **Add meeting** records a call. **Open booking form** opens the customer form. Open a row, change status, time, **Assigned to**, or notes, then **Save changes**. **Complete / Mark complete** finishes the meeting, not the sales enquiry. |
| **Conversations** | Open a chat → **Take over** → choose **Free text** or an approved message under **Message type** → **Send**. If the reply window is closed, use an approved message. **Return to bot** restarts automatic replies. **Refresh** reloads; **Load earlier messages** shows older chat. |
| **Settings** | Turn reminders and follow-ups on or off, choose when they send, then **Save settings**. Choose an approved message for sends outside the reply window. See recent attempts. **Change password** updates your password. |

**Customer booking:** Name + phone + email + date → choose a time → **Book meeting**. Your team confirms the final time.

**Advanced WhatsApp settings** is for the person managing the WhatsApp connection. **Refresh WhatsApp settings** checks it; **Copy** copies its address. **X** closes an open side panel.
