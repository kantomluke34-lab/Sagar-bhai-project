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

To send an image, video, or document in a campaign, choose that **Header type** while making the template and upload one sample file for Meta to review. Later, when you schedule the campaign, upload the actual image, video, or document.

Use `{{1}}`, `{{2}}` for details that change by person:

```text
Message:  Hello {{1}}, your meeting is on {{2}}.
Examples: Asha, Tuesday at 3 pm
```

Enter one example per number, in order, under **Variable examples**. **Pending** means Meta is reviewing it. If **Rejected**, read the reason, **Edit**, save, and submit again. **Duplicate** makes a fresh draft from an approved or pending message. Only **Approved** messages can be used in campaigns.

### 3. Make an audience and send a campaign

```text
Campaigns --> New audience --> Pick people --> Save
          --> Use in campaign --> Pick message --> Pick time --> Schedule
```

#### Step 1: Make a saved audience

1. Open **Campaigns** and select **New audience**.
2. Enter a name, such as “November customers”.
3. Tick the people you want to include.
4. Select **Save audience** if you will send later.
5. Select **Save & create campaign** if you want to continue now.

Only people marked **Opted in** are available to add. If you see **Permission changed**, that person no longer has permission to receive messages. Select **Remove** to take them out of the audience. They will not receive a campaign until they opt in again.

To change a saved audience, select **Edit**. To start sending to it, select **Use in campaign**. Deleting an audience does not change a campaign that is already scheduled.

#### Step 2: Choose who receives the message

1. In the campaign window, leave **Saved audience** selected.
2. Choose the saved audience from the list.
3. Check the number of people shown as ready to receive the message.
4. Select **New audience** to make another group, or **Edit selected** to change the chosen group.
5. If you return from editing, select **Save & return to campaign**. Your message and send time stay in place.

You can also use **CSV / Excel** to upload a list, or **Paste numbers** to enter a short list. For either one, confirm that every person agreed to WhatsApp messages and enter where and when they agreed.

#### Step 3: Choose the message and send time

1. Enter a campaign name.
2. Choose an approved message.
3. For every `{{1}}`, `{{2}}` in the message, choose the matching detail, such as name or phone number.
4. Choose **Once**, **Daily**, or **Weekly**.
5. Choose a future date and time in India time.
6. Select **Schedule campaign** and check the final message before confirming.

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
