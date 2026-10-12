import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { ApiError, api, getToken, setToken, type AuthStatus } from '../api'

interface AuthState {
  loading: boolean
  status: AuthStatus | null
  authenticated: boolean
  initialized: boolean
  login: (password: string) => Promise<void>
  setup: (password: string) => Promise<void>
  logout: () => void
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<AuthStatus | null>(null)
  const [authenticated, setAuthenticated] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const result = await api.authStatus()
      setStatus(result)
      setAuthenticated(result.authenticated)
      if (!result.authenticated) setToken(null)
    } catch (e) {
      // 后端不可用时不阻塞界面，交给页面提示
      setStatus({ initialized: true, authenticated: false, min_password_length: 8 })
      setAuthenticated(false)
      if (e instanceof ApiError) setToken(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const login = useCallback(async (password: string) => {
    const result = await api.login(password)
    setToken(result.token)
    setAuthenticated(true)
    setStatus((prev) => (prev ? { ...prev, authenticated: true } : prev))
  }, [])

  const setup = useCallback(async (password: string) => {
    const result = await api.setup(password)
    setToken(result.token)
    setAuthenticated(true)
    setStatus({ initialized: true, authenticated: true, min_password_length: 8 })
  }, [])

  const logout = useCallback(() => {
    setToken(null)
    setAuthenticated(false)
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      loading,
      status,
      authenticated,
      initialized: status?.initialized ?? false,
      login,
      setup,
      logout,
      refresh,
    }),
    [loading, status, authenticated, login, setup, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

export { getToken }
