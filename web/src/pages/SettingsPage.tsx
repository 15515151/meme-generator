import { useEffect, useState, type FormEvent } from 'react'

import { ApiError, api, publicApi } from '../api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../components/Toast'
import { Alert, Badge, Spinner } from '../components/ui'

export default function SettingsPage() {
  const toast = useToast()
  const { logout } = useAuth()
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [version, setVersion] = useState('')
  const [openapiPaths, setOpenapiPaths] = useState<number | null>(null)

  useEffect(() => {
    publicApi
      .version()
      .then((r) => setVersion(r.version))
      .catch(() => undefined)
    fetch('/openapi.json')
      .then((r) => r.json())
      .then((data) => setOpenapiPaths(Object.keys(data.paths ?? {}).length))
      .catch(() => setOpenapiPaths(null))
  }, [])

  async function changePassword(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (newPassword.length < 8) {
      setError('新密码长度至少为 8 位')
      return
    }
    if (newPassword !== confirm) {
      setError('两次输入的新密码不一致')
      return
    }
    setBusy(true)
    try {
      await api.changePassword(oldPassword, newPassword)
      toast.success('密码已修改，请使用新密码重新登录')
      setOldPassword('')
      setNewPassword('')
      setConfirm('')
      setTimeout(logout, 1200)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '修改失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">设置</h1>
        <p className="page-desc">修改管理员密码，查看服务信息与对外接口入口。</p>
      </div>

      <div className="card">
        <h2 className="card-title">服务信息</h2>
        {version ? (
          <div className="row-sub">
            服务版本：{version}
            {openapiPaths !== null && <> · 已注册接口：{openapiPaths} 个</>}
          </div>
        ) : (
          <Spinner label="读取中…" />
        )}
        <div className="btn-row" style={{ marginTop: 12 }}>
          <a className="btn btn-sm" href="/docs" target="_blank" rel="noreferrer">
            打开 API 文档
          </a>
          <a className="btn btn-sm" href="/openapi.json" target="_blank" rel="noreferrer">
            查看 OpenAPI
          </a>
        </div>
      </div>

      <div className="card">
        <h2 className="card-title">修改密码</h2>
        {error && <Alert kind="error">{error}</Alert>}
        <form onSubmit={changePassword}>
          <div className="field">
            <label htmlFor="old-password">当前密码</label>
            <input
              id="old-password"
              className="input"
              type="password"
              value={oldPassword}
              autoComplete="current-password"
              onChange={(e) => setOldPassword(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="new-password">新密码（至少 8 位）</label>
            <input
              id="new-password"
              className="input"
              type="password"
              value={newPassword}
              autoComplete="new-password"
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="confirm-password">确认新密码</label>
            <input
              id="confirm-password"
              className="input"
              type="password"
              value={confirm}
              autoComplete="new-password"
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy && <span className="spinner" />}
            修改密码
          </button>
        </form>
        <Alert kind="warn">
          修改密码后所有已签发的登录令牌都会失效，需要重新登录。
        </Alert>
      </div>

      <div className="card">
        <h2 className="card-title">公开接口</h2>
        <p className="page-desc" style={{ marginBottom: 12 }}>
          以下接口无需登录，适合下游服务查询表情清单与更新情况。
        </p>
        <div className="user-list">
          <Endpoint method="GET" path="/api/memes" desc="表情清单，支持 q 搜索与 include_disabled" />
          <Endpoint method="GET" path="/api/repos" desc="已注册的外部仓库及表情数量" />
          <Endpoint method="GET" path="/api/updates" desc="更新概览，include_content=true 时返回文件内容" />
          <Endpoint method="GET" path="/api/updates/{meme_key}" desc="单个表情的更新详情" />
          <Endpoint method="GET" path="/memes/keys" desc="已启用表情的 key 列表" />
          <Endpoint method="GET" path="/memes/{key}/info" desc="表情参数说明" />
          <Endpoint method="GET" path="/memes/{key}/preview" desc="生成预览图" />
          <Endpoint method="POST" path="/memes/{key}/" desc="生成表情（multipart/form-data）" />
        </div>
      </div>
    </>
  )
}

function Endpoint({ method, path, desc }: { method: string; path: string; desc: string }) {
  return (
    <div className="row-card">
      <div className="row-head">
        <div style={{ minWidth: 0 }}>
          <div className="row-title mono">{path}</div>
          <div className="row-sub">{desc}</div>
        </div>
        <Badge tone={method === 'GET' ? 'on' : 'info'}>{method}</Badge>
      </div>
    </div>
  )
}
