import { CalendarCheck, CalendarClock, ContactRound, MessagesSquare } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import api from '../api'

const colors = ['#ffb000', '#28c7a9', '#5b8cff', '#ef6f6c', '#a78bfa', '#94a3b8']
const human = (value = '') => value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
const when = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Kolkata' }) : 'Awaiting slot'

export default function Dashboard() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { api.get('/api/dashboard/analytics').then(({ data }) => setData(data)).catch(() => setError('Could not load dashboard data. Please refresh and try again.')) }, [])
  const stats = [
    ['CRM contacts', data?.total_contacts, ContactRound], ['Meeting requests', data?.total_meetings, MessagesSquare],
    ['Upcoming', data?.upcoming_meetings, CalendarClock], ['Today', data?.today_meetings, CalendarCheck],
  ]
  const statusRows = data?.by_status || []
  const trendRows = data?.monthly_trend || []
  return <>
    <PageTitle kicker="OPERATIONS OVERVIEW" title="Meeting intelligence" subtitle="From first WhatsApp enquiry to confirmed technical discussion." />
    {error && <div className="alert error" role="alert">{error}</div>}
    <div className="stats-grid">{stats.map(([label, value, Icon]) => <div className="stat-card" key={label}><div className="stat-icon"><Icon size={20} /></div><div><span>{label}</span><strong>{value ?? '—'}</strong></div></div>)}</div>
    <div className="chart-grid">
      <section className="panel chart-panel"><PanelTitle title="Meeting requests by status" subtitle="Every meeting is counted once by its current status." />{statusRows.length ? <><ResponsiveContainer width="100%" height={260}><PieChart><Pie data={statusRows} dataKey="count" nameKey="status" innerRadius={58} outerRadius={96} paddingAngle={3}>{statusRows.map((_, index) => <Cell key={index} fill={colors[index % colors.length]} />)}</Pie><Tooltip formatter={(value, name) => [value, human(name)]} /></PieChart></ResponsiveContainer><Legend rows={statusRows} labelKey="status" /></> : <ChartEmpty message="Meeting status totals will appear after the first request." />}</section>
      <section className="panel chart-panel"><PanelTitle title="Monthly request trend" subtitle="New meeting requests created each month." />{trendRows.length ? <ResponsiveContainer width="100%" height={300}><BarChart data={trendRows}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#dce2ea" /><XAxis dataKey="month" tick={{ fontSize: 12 }} /><YAxis allowDecimals={false} tick={{ fontSize: 12 }} /><Tooltip /><Bar dataKey="count" fill="#ffb000" radius={[8, 8, 0, 0]} /></BarChart></ResponsiveContainer> : <ChartEmpty message="Monthly activity will appear after meetings are created." />}</section>
    </div>
    <section className="panel"><PanelTitle title="Recent meeting requests" /><div className="table-wrap"><table><thead><tr><th>Contact</th><th>Interest</th><th>Preferred time</th><th>Source</th><th>Status</th></tr></thead><tbody>{(data?.recent_meetings || []).map((item) => <tr key={item.id}><td><strong>{item.name}</strong><small>{item.company || item.phone}</small></td><td>{item.interest || 'General enquiry'}</td><td>{when(item.start_at)}</td><td>{human(item.source)}</td><td><Status value={item.status} /></td></tr>)}</tbody></table></div></section>
  </>
}

export function PageTitle({ kicker, title, subtitle, action }) { return <header className="page-title"><div><span className="eyebrow">{kicker}</span><h1>{title}</h1><p>{subtitle}</p></div>{action}</header> }
function PanelTitle({ title, subtitle }) { return <div className="panel-title"><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div> }
function ChartEmpty({ message }) { return <div className="chart-empty">{message}</div> }
function Legend({ rows, labelKey }) { return <div className="legend">{rows.map((row, index) => <span key={row[labelKey]}><i style={{ background: colors[index % colors.length] }} />{human(row[labelKey])} <b>{row.count}</b></span>)}</div> }
export function Status({ value }) { return <span className={`status status-${value}`}>{human(value)}</span> }
