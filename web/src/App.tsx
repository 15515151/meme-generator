import { useEffect, useState } from 'react'

import { api, type Health } from './api'
import { useAuth } from './context/AuthContext'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import MemesPage from './pages/MemesPage'
import ReposPage from './pages/ReposPage'
import UpdatesPage from './pages/UpdatesPage'
import SettingsPage from './pages/SettingsPage'
import { Spinner } from './components/ui'

type Tab = 'dashboard' | 'memes' | 'repos' | 'updates' | 'settings'

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: 'dashboard', label: '概览', icon: '📊' },
  { id: 'memes', label: '表情', icon: '🖼' },
  { id: 'repos', label: '仓库', icon: '📦' },
  { id: 'updates', label: '更新', icon: '⬆' },
  { id: 'settings', label: '设置', icon: '⚙' },
]

export default function App() {
  const { loading, authenticated, logout } = useAuth()
  const [tab, setTab] = useState<Tab>('dashboard')
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    if (!authenticated) {
      setHealth(null)
      return
    }
    let cancelled = false
    api
      .health()
      .then((result) => {
        if (!cancelled) setHealth(result)
      })
      .catch(() => {
        /* 概览数据失败不影响其它页面 */
      })
    return () => {
      cancelled = true
    }
  }, [authenticated, tab])

  if (loading) {
    return (
      <div className="auth-page">
        <Spinner label="正在连接服务…" />
      </div>
    )
  }

  if (!authenticated) {
    return <LoginPage />
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <span className="dot" />
          表情管理控制台
        </div>
        <nav className="nav-desktop">
          {TABS.map((item) => (
            <button
              key={item.id}
              className={tab === item.id ? 'active' : ''}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="topbar-spacer" />
        <button className="btn btn-sm" onClick={logout}>
          退出
        </button>
      </header>

      <main className="content">
        {tab === 'dashboard' && (
          <DashboardPage health={health} onNavigate={(next) => setTab(next as Tab)} />
        )}
        {tab === 'memes' && <MemesPage />}
        {tab === 'repos' && <ReposPage />}
        {tab === 'updates' && <UpdatesPage />}
        {tab === 'settings' && <SettingsPage />}
      </main>

      <nav className="nav-bottom">
        {TABS.map((item) => (
          <button
            key={item.id}
            className={tab === item.id ? 'active' : ''}
            onClick={() => setTab(item.id)}
          >
            <span className="icon" aria-hidden>
              {item.icon}
            </span>
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
    </div>
  )
}
