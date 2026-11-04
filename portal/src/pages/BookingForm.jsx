import { addDays, format } from 'date-fns'
import { CalendarDays, CheckCircle2, Clock3, Loader2, MapPin } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { publicApi } from '../api'

const initial = {
  name: '',
  phone: '',
  email: '',
  meeting_date: '',
  start_time: '',
}

export default function BookingForm() {
  const [params] = useSearchParams()
  const [config, setConfig] = useState(null)
  const [form, setForm] = useState(() => ({
    ...initial,
    name: params.get('name') || '',
    phone: params.get('phone') || '',
    interest: params.get('interest') || 'General enquiry',
    purpose: params.get('purpose') || 'Meeting requested through the booking form',
  }))
  const [slots, setSlots] = useState([])
  const [loadingSlots, setLoadingSlots] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(null)

  useEffect(() => {
    publicApi.get('/api/public/config')
      .then(({ data }) => setConfig(data))
      .catch(() => setError('Booking form is temporarily unavailable.'))
  }, [])

  useEffect(() => {
    if (!form.meeting_date) {
      setSlots([])
      return
    }
    let active = true
    setLoadingSlots(true)
    setError('')
    setForm((value) => ({ ...value, start_time: '' }))
    publicApi.get('/api/public/slots', { params: { date: form.meeting_date } })
      .then(({ data }) => active && setSlots(data))
      .catch(() => { if (active) { setSlots([]); setError('Could not load available times. Please try another date.') } })
      .finally(() => active && setLoadingSlots(false))
    return () => { active = false }
  }, [form.meeting_date])

  const minDate = format(new Date(), 'yyyy-MM-dd')
  const maxDate = format(addDays(new Date(), 60), 'yyyy-MM-dd')
  const selectedLabel = useMemo(
    () => slots.find((slot) => slot.start_time === form.start_time)?.label,
    [slots, form.start_time],
  )
  const set = (key) => (event) => setForm((value) => ({ ...value, [key]: event.target.value }))

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { data } = await publicApi.post('/api/public/meetings', form)
      setSuccess(data)
    } catch (requestError) {
      const detail = requestError.response?.data?.detail
      setError(Array.isArray(detail) ? detail[0]?.msg : detail || 'Could not submit the meeting request.')
    } finally {
      setBusy(false)
    }
  }

  if (success) {
    return (
      <div className="booking-shell">
        <div className="success-card">
          <CheckCircle2 size={44} />
          <span className="eyebrow">REQUEST #{success.meeting_id}</span>
          <h1>Your meeting is requested.</h1>
          <p>{format(new Date(success.start_at), 'EEEE, dd MMMM yyyy · h:mm a')}</p>
          <div className="info-strip"><MapPin size={18} />Mechman Solutions, Vadodara</div>
          <p className="muted">We’ll confirm it on WhatsApp or phone and remind you before the call.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="booking-shell">
      <header className="booking-header">
        <div className="brand-mark">MS</div>
        <div><strong>Book a meeting</strong><span>Mechman Solutions · Vadodara</span></div>
      </header>
      <form className="booking-card simple-booking" onSubmit={submit}>
        <div className="form-intro">
          <span className="eyebrow">BOOK A CALL</span>
          <h1>Pick a convenient time.</h1>
          <p>Just four details. We’ll take it from there.</p>
        </div>
        {error && <div className="alert error">{error}</div>}
        <div className="form-grid">
          <label>Full name *<input value={form.name} onChange={set('name')} autoComplete="name" required /></label>
          <label>Phone number *<input value={form.phone} onChange={set('phone')} inputMode="tel" autoComplete="tel" required /></label>
          <label className="span-2">Email address *<input type="email" value={form.email} onChange={set('email')} autoComplete="email" required /></label>
          <label>Meeting date *<input type="date" min={minDate} max={maxDate} value={form.meeting_date} onChange={set('meeting_date')} required /></label>
          <div className="field">
            <span>Meeting time *</span>
            <div className="slots">
              {loadingSlots ? (
                <span className="muted"><Loader2 className="spin" size={16} /> Loading…</span>
              ) : slots.length ? slots.map((slot) => (
                <button
                  type="button"
                  key={slot.start_time}
                  className={form.start_time === slot.start_time ? 'slot selected' : 'slot'}
                  onClick={() => setForm((value) => ({ ...value, start_time: slot.start_time }))}
                >
                  <Clock3 size={14} />{slot.label}
                </button>
              )) : (
                <span className="muted">{form.meeting_date ? 'No slots available.' : 'Choose a date first.'}</span>
              )}
            </div>
            <input type="hidden" value={form.start_time} required />
          </div>
        </div>
        <div className="booking-summary">
          <CalendarDays size={18} />
          <span>{selectedLabel && form.meeting_date
            ? `${format(new Date(`${form.meeting_date}T00:00:00`), 'EEEE, dd MMM')} at ${selectedLabel}`
            : config?.business_hours || 'Monday–Saturday business hours'}</span>
        </div>
        <button className="primary-button wide" disabled={busy || !form.start_time}>
          {busy ? 'Submitting…' : 'Book meeting'}
        </button>
        <p className="fine-print">The Mechman team will confirm the final slot.</p>
      </form>
    </div>
  )
}
