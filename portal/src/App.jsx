import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Layout from './components/Layout'

const BookingForm = lazy(() => import('./pages/BookingForm'))
const Campaigns = lazy(() => import('./pages/Campaigns'))
const Conversations = lazy(() => import('./pages/Conversations'))
const CRM = lazy(() => import('./pages/CRM'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Login = lazy(() => import('./pages/Login'))
const Meetings = lazy(() => import('./pages/Meetings'))
const Settings = lazy(() => import('./pages/Settings'))
const Templates = lazy(() => import('./pages/Templates'))
const Waba = lazy(() => import('./pages/Waba'))
const WebhookStatus = lazy(() => import('./pages/WebhookStatus'))

function Protected() {
  const { user, loading } = useAuth()
  if (loading) return <div className="screen-center">Loading dashboard…</div>
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Suspense fallback={<div className="screen-center">Loading…</div>}>
          <Routes>
            <Route path="/book" element={<BookingForm />} />
            <Route path="/login" element={<Login />} />
            <Route element={<Protected />}>
              <Route element={<Layout />}>
                <Route index element={<Dashboard />} />
                <Route path="/conversations" element={<Conversations />} />
                <Route path="/campaigns" element={<Campaigns />} />
                <Route path="/meetings" element={<Meetings />} />
                <Route path="/crm" element={<CRM />} />
                <Route path="/waba" element={<Waba />} />
                <Route path="/templates" element={<Templates />} />
                <Route path="/webhook-status" element={<WebhookStatus />} />
                <Route path="/whatsapp" element={<Navigate to="/waba" replace />} />
                <Route path="/settings" element={<Settings />} />
              </Route>
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  )
}
