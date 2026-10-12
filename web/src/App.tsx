import { useEffect, useState, type ReactElement } from 'react'

import { api, type Health } from './api'
import { useAuth } from './context/AuthContext'
import { useTheme } from './context/ThemeContext'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import MemesPage from './pages/MemesPage'
import ReposPage from './pages/ReposPage'
import UpdatesPage from './pages/UpdatesPage'
import SettingsPage from './pages/SettingsPage'
import ApiDocsPage from './pages/ApiDocsPage'
import { Spinner } from './components/ui'
import {
  IconDashboard,
  IconLogout,
  IconMeme,
  IconMoon,
  IconRepo,
  IconServer,
  IconSettings,
  IconSun,
  IconUpdate,
} from './components/icons'

type Tab = 'dashboard' | 'memes' | 'repos' | 'updates' | 'settings' | 'docs'

const NAV: {
  id: Tab
  label: string
  icon: (props: { size?: number }) => ReactElement
  title: string
  sub: string
}[] = [
  {
    id: 'dashboard',
    label: '概览',
    icon: IconDashboard,
    title: '概览',
    sub: '服务状态与快捷操作',
  },
  { id: 'memes', label: '表情管理', icon: IconMeme, title: '表情管理', sub: '预览、搜索与封禁' },
  { id: 'repos', label: '外部仓库', icon: IconRepo, title: '外部仓库', sub: '添加与同步第三方表情' },
  { id: 'updates', label: '更新检查', icon: IconUpdate, title: '更新检查', sub: '查看并应用仓库变更' },
  { id: 'settings', label: '设置', icon: IconSettings, title: '设置', sub: '账号与接口信息' },
]

const DOCS_NAV = {
  id: 'docs' as Tab,
  label: 'API 文档',
  icon: IconServer,
  title: 'API 文档',
  sub: '接口说明与请求示例',
}

export default function App() {
  const { loading, authenticated, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const [tab, setTab] = useState<Tab>('dashboard')
  const [health, setHealth] = useState<Health | null>(null)
  const [pendingUpdates, setPendingUpdates] = useState<number | null>(null)
  const [apiDomain, setApiDomain] = useState('')

  useEffect(() => {
    if (!authenticated) {
      setHealth(null)
      setPendingUpdates(null)
      return
    }
    let cancelled = false
    api
      .health()
      .then((result) => {
        if (!cancelled) setHealth(result)
      })
      .catch(() => {
        /* 概览失败不影响其它页面 */
      })
    return () => {
      cancelled = true
    }
  }, [authenticated, tab, apiDomain])

  // 读取配置的对外地址，API 文档的示例要用它
  useEffect(() => {
    if (!authenticated) return
    let cancelled = false
    api
      .getSettings()
      .then((result) => {
        if (!cancelled) setApiDomain(result.server.api_domain)
      })
      .catch(() => {
        /* 读取失败时文档退回当前地址 */
      })
    return () => {
      cancelled = true
    }
  }, [authenticated, apiDomain])

  // 后台静默检查更新，给侧边栏一个待处理数量
  useEffect(() => {
    if (!authenticated) return
    let cancelled = false
    api
      .checkUpdates()
      .then((result) => {
        if (!cancelled) setPendingUpdates(result.updated)
      })
      .catch(() => {
        /* 检查失败时不展示角标 */
      })
    return () => {
      cancelled = true
    }
  }, [authenticated])

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

  const current = tab === 'docs' ? DOCS_NAV : (NAV.find((item) => item.id === tab) ?? NAV[0])

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <img className="brand-mark" src="/logo.png" alt="" />
          <span className="brand-text">表情管理控制台</span>
        </div>

        <nav className="sidebar-nav">
          <div className="nav-section">管理</div>
          {NAV.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.id}
                className={`nav-item${tab === item.id ? ' active' : ''}`}
                onClick={() => setTab(item.id)}
              >
                <span className="nav-icon">
                  <Icon size={17} />
                </span>
                <span>{item.label}</span>
                {item.id === 'updates' && pendingUpdates ? (
                  <span className="nav-badge">{pendingUpdates}</span>
                ) : null}
              </button>
            )
          })}

          <div className="nav-section">开发</div>
          <button
            className={`nav-item${tab === 'docs' ? ' active' : ''}`}
            onClick={() => setTab('docs')}
          >
            <span className="nav-icon">
              <IconServer size={17} />
            </span>
            <span>API 文档</span>
          </button>
        </nav>

        <div className="sidebar-foot">
          <button className="theme-toggle" onClick={toggle}>
            {theme === 'dark' ? <IconSun size={16} /> : <IconMoon size={16} />}
            <span className="theme-label">{theme === 'dark' ? '浅色模式' : '深色模式'}</span>
          </button>
          <button className="theme-toggle" onClick={logout}>
            <IconLogout size={16} />
            <span className="theme-label">退出登录</span>
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="main-header">
          <h1>{current.title}</h1>
          <span className="sub">{current.sub}</span>
          <div className="header-spacer" />
          {health && (
            <span className="badge" title="服务版本">
              v{health.version}
            </span>
          )}
          {/* 右上角直达接口文档 */}
          <button
            className={`btn btn-sm${tab === 'docs' ? ' btn-primary' : ''}`}
            onClick={() => setTab('docs')}
            title="查看 API 文档"
          >
            <IconServer size={14} />
            API 文档
          </button>
          <button
            className="btn btn-ghost btn-icon"
            onClick={toggle}
            title={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
            aria-label="切换主题"
          >
            {theme === 'dark' ? <IconSun size={17} /> : <IconMoon size={17} />}
          </button>
          <button className="btn btn-sm" onClick={logout}>
            退出
          </button>
        </header>

        <main className="page">
          {tab === 'dashboard' && (
            <DashboardPage
              health={health}
              onNavigate={(next) => setTab(next as Tab)}
              pendingUpdates={pendingUpdates}
              onUpdatesChecked={setPendingUpdates}
            />
          )}
          {tab === 'memes' && <MemesPage />}
          {tab === 'repos' && <ReposPage onChanged={() => setPendingUpdates(null)} />}
          {tab === 'updates' && (
            <UpdatesPage onApplied={() => setPendingUpdates(null)} onNavigate={(next) => setTab(next as Tab)} />
          )}
          {tab === 'settings' && (
            <SettingsPage apiDomain={apiDomain} onApiDomainChange={setApiDomain} />
          )}
          {tab === 'docs' && <ApiDocsPage apiDomain={apiDomain} />}
        </main>
      </div>

      <nav className="mobile-bar">
        {NAV.map((item) => {
          const Icon = item.icon
          return (
            <button
              key={item.id}
              className={tab === item.id ? 'active' : ''}
              onClick={() => setTab(item.id)}
            >
              <span className="icon">
                <Icon size={18} />
              </span>
              <span>{item.label}</span>
            </button>
          )
        })}
      </nav>
    </div>
  )
}
