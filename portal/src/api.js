import axios from 'axios'

const TOKEN_KEY = 'mechman_crm_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (value) => localStorage.setItem(TOKEN_KEY, value)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

export const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const usesLoopbackApi = /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(?::|\/|$)/.test(API_BASE_URL)
const transport = usesLoopbackApi
  ? { adapter: 'fetch', fetchOptions: { targetAddressSpace: 'loopback' } }
  : {}

const api = axios.create({ baseURL: API_BASE_URL, ...transport })
api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const isPublicBookingPage = window.location.pathname === '/book'
    if (
      error.response?.status === 401
      && !window.location.pathname.startsWith('/login')
      && !isPublicBookingPage
    ) {
      clearToken()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  },
)

export const publicApi = axios.create({ baseURL: API_BASE_URL, ...transport })
export default api
