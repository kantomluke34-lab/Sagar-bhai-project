import { ArrowDown, CheckCircle2, Copy, Database, MessageCircle, RefreshCw, ShieldCheck, Webhook } from 'lucide-react'
import { useEffect, useState } from 'react'
import api, { API_BASE_URL } from '../api'
import { PageTitle } from './Dashboard'

const yes = (value) => value === true || ['configured', 'verified', 'active', 'ready'].includes(String(value || '').toLowerCase())

export default function WebhookStatus() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const callbackUrl = `${API_BASE_URL || window.location.origin}/webhook`

  async function load() {
    setError('')
    try { const { data } = await api.get('/api/waba/status'); setStatus(data) }
    catch (requestError) { setError(requestError.response?.data?.detail || 'Could not read webhook configuration.') }
  }
  useEffect(() => { load() }, [])
  async function copy() { await navigator.clipboard.writeText(callbackUrl); setCopied(true); setTimeout(() => setCopied(false), 1800) }

  const tokenReady = yes(status?.verify_token_configured) || yes(status?.webhook_verify_token_configured)
  const signatureReady = yes(status?.app_secret_configured) || yes(status?.webhook_signature_configured)
  return <>
    <PageTitle kicker="META EVENT DELIVERY" title="Webhook" subtitle="The production callback that verifies Meta and processes inbound WhatsApp events." action={<button className="secondary-button" onClick={load}><RefreshCw size={16} />Refresh</button>} />
    {error && <div className="alert error">{error}</div>}
    <section className="panel webhook-panel">
      <div className="settings-heading"><Webhook /><div><h2>Production callback URL</h2><p>Enter this exact HTTPS URL in Meta → WhatsApp → Configuration.</p></div></div>
      <div className="copy-field"><input aria-label="Webhook callback URL" readOnly value={callbackUrl} /><button className="secondary-button" onClick={copy}><Copy size={15} />{copied ? 'Copied' : 'Copy'}</button></div>
      <div className="health-grid webhook-health">
        <div className={`health-item ${tokenReady ? 'healthy' : 'unhealthy'}`}><span><CheckCircle2 /></span><div><small>GET verification</small><strong>{tokenReady ? 'Token configured' : 'Check server token'}</strong></div></div>
        <div className={`health-item ${signatureReady ? 'healthy' : 'unhealthy'}`}><span><ShieldCheck /></span><div><small>POST authenticity</small><strong>{signatureReady ? 'Signature protected' : 'Check app secret'}</strong></div></div>
      </div>
    </section>
    <section className="panel"><div className="panel-title"><h2>Event flow</h2></div><div className="webhook-flow"><div><MessageCircle /><strong>Meta WhatsApp</strong><small>messages & statuses</small></div><ArrowDown /><div><Webhook /><strong>Verified webhook</strong><small>dedupe & route</small></div><ArrowDown /><div><Database /><strong>CRM workspace</strong><small>conversation history</small></div></div></section>
    <section className="notice"><strong>Required Meta subscription</strong><p>Subscribe the app to the <code>messages</code> field for the production WABA. The verification token and app secret stay on the backend and are never displayed in this dashboard.</p></section>
  </>
}
