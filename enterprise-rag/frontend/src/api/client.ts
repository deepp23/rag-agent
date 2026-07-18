import axios from 'axios'

const TOKEN_KEY = 'rag_access_token'

// In dev, relative '/api/v1' goes through the Vite proxy (vite.config.ts).
// In prod there's no proxy, so the deployed backend's URL is baked in at
// build time via VITE_API_BASE_URL (see .github/workflows/deploy.yml).
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const client = axios.create({
  baseURL: API_BASE,
})

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

client.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearToken()
      if (location.pathname !== '/login') {
        location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((d) => d.msg).join(', ')
    if (error.message) return error.message
  }
  return 'Something went wrong. Please try again.'
}
