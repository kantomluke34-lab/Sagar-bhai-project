import { Bot, Headphones, Loader2, RefreshCw, Search, Send, UserRound, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import api from '../api'
import { PageTitle, Status } from './Dashboard'

const first = (...values) => values.find((value) => value !== undefined && value !== null && value !== '')
const when = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : 'No activity yet'
const person = (row = {}) => first(row.contact_name, row.profile_name, row.name, row.phone, row.wa_id, 'Unknown contact')
const phone = (row = {}) => first(row.phone, row.wa_id, row.contact_phone, '—')
const preview = (row = {}) => first(row.last_message, row.last_message_text, row.preview, row.message, 'No messages yet')
const isHuman = (row = {}) => Boolean(first(row.is_taken_over, row.human_takeover, row.is_manual, row.mode === 'human', row.control_mode === 'human'))
const messageText = (message = {}) => first(message.text, message.body, message.content, message.message, '')
const incoming = (message = {}) => first(message.direction, message.type) === 'inbound' || message.is_inbound === true || message.from_customer === true

function normalizeDetail(data) {
  if (data?.conversation) return { ...data.conversation, messages: data.messages || data.conversation.messages || [] }
  return { ...data, messages: data?.messages || [] }
}

export default function Conversations() {
  const [rows, setRows] = useState([])
  const [q, setQ] = useState('')
  const [selected, setSelected] = useState(null)
  const [reply, setReply] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function load() {
    setLoading(true); setError('')
    try {
      const { data } = await api.get('/api/conversations', { params: { q } })
      setRows(Array.isArray(data) ? data : data?.items || data?.conversations || [])
    } catch (requestError) {
      setError(requestError.response?.data?.detail || 'Could not load WhatsApp conversations.')
    } finally { setLoading(false) }
  }

  useEffect(() => { const timer = setTimeout(load, 250); return () => clearTimeout(timer) }, [q])

  async function open(id) {
    setError('')
    try { const { data } = await api.get(`/api/conversations/${id}`); setSelected(normalizeDetail(data)) }
    catch (requestError) { setError(requestError.response?.data?.detail || 'Could not open this conversation.') }
  }

  async function changeControl(action) {
    setBusy(true); setError('')
    try {
      await api.post(`/api/conversations/${selected.id}/${action}`)
      await open(selected.id); await load()
    } catch (requestError) { setError(requestError.response?.data?.detail || 'Could not change conversation control.') }
    finally { setBusy(false) }
  }

  async function send(event) {
    event.preventDefault()
    if (!reply.trim()) return
    setBusy(true); setError('')
    try {
      await api.post(`/api/conversations/${selected.id}/messages`, { text: reply.trim(), template_id: null, parameters: [] })
      setReply(''); await open(selected.id); await load()
    } catch (requestError) { setError(requestError.response?.data?.detail || 'Message could not be sent.') }
    finally { setBusy(false) }
  }

  const messages = selected?.messages || []
  return <>
    <PageTitle kicker="WHATSAPP INBOX" title="Conversations" subtitle="Monitor inbound enquiries, take over from automation, and reply from the CRM." action={<button className="secondary-button" onClick={load}><RefreshCw size={16} />Refresh</button>} />
    {error && <div className="alert error">{error}</div>}
    <div className="conversation-shell">
      <section className="conversation-list panel no-pad">
        <label className="search conversation-search"><Search size={17} /><input value={q} onChange={(event) => setQ(event.target.value)} placeholder="Search name, phone, or message…" aria-label="Search conversations" /></label>
        {loading ? <div className="empty"><Loader2 className="spin" size={20} /> Loading conversations…</div> : rows.length ? rows.map((row) => (
          <button key={row.id} className={`conversation-row ${selected?.id === row.id ? 'active' : ''}`} onClick={() => open(row.id)}>
            <span className="conversation-avatar">{person(row).slice(0, 1).toUpperCase()}</span>
            <span className="conversation-copy"><strong>{person(row)}</strong><small>{preview(row)}</small><em>{when(first(row.last_message_at, row.updated_at, row.created_at))}</em></span>
            <span className={`control-dot ${isHuman(row) ? 'human' : 'bot'}`} title={isHuman(row) ? 'Human controlled' : 'Bot controlled'} />
          </button>
        )) : <div className="empty">No conversations match this search.</div>}
      </section>
      <section className="conversation-detail panel no-pad">
        {selected ? <>
          <header className="conversation-head">
            <div><strong>{person(selected)}</strong><span>{phone(selected)}</span></div>
            <div className="conversation-actions">
              <span className="control-label">{isHuman(selected) ? <><Headphones size={15} />Human control</> : <><Bot size={15} />Bot control</>}</span>
              {isHuman(selected)
                ? <button disabled={busy} className="secondary-button compact" onClick={() => changeControl('return-to-bot')}>Return to bot</button>
                : <button disabled={busy} className="primary-button compact" onClick={() => changeControl('take-over')}>Take over</button>}
              <button className="icon-button mobile-detail-close" aria-label="Close conversation" onClick={() => setSelected(null)}><X /></button>
            </div>
          </header>
          <div className="message-stream">
            {messages.length ? messages.map((message, index) => (
              <article key={message.id || index} className={`message-bubble ${incoming(message) ? 'inbound' : 'outbound'}`}>
                <p>{messageText(message)}</p>
                <small>{when(first(message.occurred_at, message.sent_at, message.created_at, message.timestamp))}</small>
              </article>
            )) : <div className="empty"><UserRound size={24} /> No messages in this conversation yet.</div>}
          </div>
          <form className="message-composer" onSubmit={send}>
            <textarea aria-label="Reply message" rows="2" value={reply} onChange={(event) => setReply(event.target.value)} placeholder={isHuman(selected) ? 'Type a WhatsApp reply…' : 'Take over to send a manual reply…'} disabled={!isHuman(selected) || busy} />
            <button className="primary-button" disabled={!isHuman(selected) || busy || !reply.trim()}><Send size={16} />Send</button>
          </form>
        </> : <div className="conversation-placeholder"><Bot size={34} /><h2>Select a conversation</h2><p>Messages and control options will appear here.</p></div>}
      </section>
    </div>
  </>
}
