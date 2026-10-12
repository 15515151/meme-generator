import { useEffect, useState, type FormEvent } from 'react'

import { ApiError, api, publicApi } from '../api'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { useToast } from '../components/Toast'
import { Alert, Badge, Card, Spinner, Switch } from '../components/ui'
import { IconCode, IconLock, IconMoon, IconServer, IconSun } from '../components/icons'

export default function SettingsPage() {
  const toast = useToast()
  const { logout } = useAuth()
  const { theme, setTheme } = useTheme()
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

  const publicEndpoints = [
    { method: 'GET', path: '/api/memes', desc: '表情清单，支持 q 搜索与 include_disabled' },
    { method: 'GET', path: '/api/repos', desc: '已注册的外部仓库及表情数量' },
    { method: 'GET', path: '/api/updates', desc: '更新概览，include_content=true 返回文件内容' },
    { method: 'GET', path: '/api/updates/{meme_key}', desc: '单个表情的更新详情' },
    { method: 'GET', path: '/memes/keys', desc: '已启用表情的 key 列表' },
    { method: 'GET', path: '/memes/{key}/info', desc: '表情参数说明' },
    { method: 'GET', path: '/memes/{key}/preview', desc: '生成预览图' },
    { method: 'POST', path: '/memes/{key}/', desc: '生成表情（multipart/form-data）' },
  ]

  return (
    <div className="grid-2" style={{ alignItems: 'start' }}>
      <div>
        <Card title="外观" pad>
          <div className="row between">
            <div className="row">
              {theme === 'dark' ? <IconMoon size={16} /> : <IconSun size={16} />}
              <span style={{ fontWeight: 550 }}>深色模式</span>
            </div>
            <Switch
              checked={theme === 'dark'}
              onChange={(next) => setTheme(next ? 'dark' : 'light')}
              label={theme === 'dark' ? '已开启' : '已关闭'}
            />
          </div>
          <p className="text-sm text-muted mt-3 mb-0">
            主题偏好保存在本地浏览器，也可跟随系统设置。
          </p>
        </Card>

        <Card title="服务信息" pad>
          {version ? (
            <dl className="kv">
              <dt>服务版本</dt>
              <dd className="mono">{version}</dd>
              <dt>已注册接口</dt>
              <dd>{openapiPaths !== null ? `${openapiPaths} 个` : '—'}</dd>
              <dt>管理凭据</dt>
              <dd>PBKDF2-HMAC-SHA256 加盐哈希</dd>
              <dt>登录令牌</dt>
              <dd>HMAC 签名，有效期 7 天</dd>
            </dl>
          ) : (
            <Spinner label="读取中…" />
          )}
          <div className="btn-row mt-4">
            <a className="btn btn-sm" href="/docs" target="_blank" rel="noreferrer">
              <IconServer size={14} />
              API 文档
            </a>
            <a className="btn btn-sm" href="/openapi.json" target="_blank" rel="noreferrer">
              <IconCode size={14} />
              OpenAPI
            </a>
          </div>
        </Card>

        <Card title="修改密码" pad>
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
              {busy ? <span className="spinner" /> : <IconLock size={14} />}
              修改密码
            </button>
          </form>
          <div className="mt-3">
            <Alert kind="warn">修改密码后所有已签发的登录令牌都会失效，需要重新登录。</Alert>
          </div>
        </Card>
      </div>

      <div>
        <Card
          title="公开接口"
          count={`（${publicEndpoints.length}）`}
          pad
        >
          <p className="text-sm text-muted mb-4">
            以下接口无需登录，适合下游服务查询表情清单与更新情况。
          </p>
          <div className="list">
            {publicEndpoints.map((endpoint) => (
              <div key={endpoint.path} className="file-row" style={{ alignItems: 'flex-start' }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="mono" style={{ wordBreak: 'break-all' }}>
                    {endpoint.path}
                  </div>
                  <div className="text-dim" style={{ fontSize: 11.5, marginTop: 2 }}>
                    {endpoint.desc}
                  </div>
                </div>
                <Badge tone={endpoint.method === 'GET' ? 'on' : 'info'}>{endpoint.method}</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card title="错误响应格式" pad>
          <p className="text-sm text-muted mb-3">
            所有错误都返回统一结构，可按下游逻辑按 <code className="mono">error.code</code> 分支处理。
          </p>
          <pre className="code-block">{`{
  "error": {
    "code": "NO_SUCH_MEME",
    "message": "表情“xxx”不存在",
    "status_code": 531,
    "context": { "meme_key": "xxx" }
  },
  "detail": "表情“xxx”不存在"
}`}</pre>
          <div className="row mt-3" style={{ gap: 5 }}>
            {['NO_SUCH_MEME', 'MEME_DISABLED', 'VALIDATION_ERROR', 'UNAUTHORIZED', 'REPO_FETCH_FAILED'].map(
              (code) => (
                <Badge key={code} tone="info">
                  {code}
                </Badge>
              ),
            )}
          </div>
        </Card>

        <Card title="数据目录" pad>
          <p className="text-sm text-muted mb-3">以下内容保存在服务端数据目录，可在环境变量中重定向。</p>
          <div className="file-row">
            <span className="file-path">admin.json</span>
            <span className="file-size">管理员凭据</span>
          </div>
          <div className="file-row">
            <span className="file-path">repos/</span>
            <span className="file-size">同步的外部仓库</span>
          </div>
          <div className="file-row">
            <span className="file-path">config.toml</span>
            <span className="file-size">配置与封禁列表</span>
          </div>
          <div className="mt-3">
            <Alert kind="info">
              忘记密码时删除 <code className="mono">admin.json</code> 并重启服务即可重新初始化。
            </Alert>
          </div>
        </Card>
      </div>
    </div>
  )
}
