import { useEffect, useState, type FormEvent } from 'react'

import { ApiError, api, publicApi } from '../api'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { useToast } from '../components/Toast'
import { Alert, Badge, Card, Spinner, Switch } from '../components/ui'
import { ProxyPicker } from '../components/ProxyPicker'
import { IconCheck, IconCode, IconLock, IconMoon, IconServer, IconSun } from '../components/icons'

export default function SettingsPage({
  apiDomain,
  onApiDomainChange,
}: {
  apiDomain: string
  onApiDomainChange: (value: string) => void
}) {
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
  const [domainDraft, setDomainDraft] = useState(apiDomain)
  const [savingDomain, setSavingDomain] = useState(false)
  const [domainError, setDomainError] = useState('')
  const [proxyDraft, setProxyDraft] = useState('')
  const [globalProxy, setGlobalProxy] = useState('')
  const [proxyPresets, setProxyPresets] = useState<string[]>([])
  const [savingProxy, setSavingProxy] = useState(false)
  const [proxyError, setProxyError] = useState('')

  useEffect(() => {
    setDomainDraft(apiDomain)
  }, [apiDomain])

  useEffect(() => {
    api
      .getSettings()
      .then((r) => {
        setProxyDraft(r.repo.github_proxy)
        setGlobalProxy(r.repo.effective_proxy)
        setProxyPresets(r.repo.proxy_presets)
      })
      .catch(() => undefined)
  }, [])

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

  async function saveDomain(e: FormEvent) {
    e.preventDefault()
    setDomainError('')
    const value = domainDraft.trim()
    if (value && !/^https?:\/\//.test(value)) {
      setDomainError('地址需要以 http:// 或 https:// 开头')
      return
    }
    setSavingDomain(true)
    try {
      const result = await api.updateSettings({ api_domain: value })
      onApiDomainChange(result.server.api_domain)
      setDomainDraft(result.server.api_domain)
      toast.success(
        result.server.api_domain ? 'API 域名已保存' : '已清空，API 文档将使用当前地址',
      )
    } catch (e) {
      setDomainError(e instanceof ApiError ? e.message : '保存失败')
    } finally {
      setSavingDomain(false)
    }
  }

  async function saveProxy(e: FormEvent) {
    e.preventDefault()
    setProxyError('')
    setSavingProxy(true)
    try {
      const result = await api.updateSettings({ github_proxy: proxyDraft.trim() })
      setProxyDraft(result.repo.github_proxy)
      setGlobalProxy(result.repo.effective_proxy)
      toast.success(
        result.repo.effective_proxy
          ? `全局加速源已设置为 ${result.repo.effective_proxy}`
          : '已改为直连 GitHub',
      )
    } catch (e) {
      setProxyError(e instanceof ApiError ? e.message : '保存失败')
    } finally {
      setSavingProxy(false)
    }
  }

  const effectiveBase = apiDomain || (typeof window !== 'undefined' ? window.location.origin : '')

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

        <Card title="API 域名" pad>
          <p className="text-sm text-muted mb-4">
            配置后，API 文档里的请求地址与 cURL 示例会使用这个域名，方便把接口说明直接发给调用方。
            留空则使用当前访问地址。
          </p>
          {domainError && <Alert kind="error">{domainError}</Alert>}
          <form onSubmit={saveDomain}>
            <div className="field">
              <label htmlFor="api-domain">对外访问地址</label>
              <input
                id="api-domain"
                className="input"
                value={domainDraft}
                placeholder="https://meme.example.com"
                spellCheck={false}
                onChange={(e) => setDomainDraft(e.target.value)}
              />
              <span className="field-hint">
                需要带协议头。当前示例地址：<code className="mono">{effectiveBase}</code>
              </span>
            </div>
            <div className="btn-row">
              <button className="btn btn-primary" type="submit" disabled={savingDomain}>
                {savingDomain ? <span className="spinner" /> : <IconCheck size={14} />}
                保存
              </button>
              {domainDraft !== apiDomain && (
                <button
                  className="btn"
                  type="button"
                  onClick={() => setDomainDraft(apiDomain)}
                  disabled={savingDomain}
                >
                  撤销
                </button>
              )}
            </div>
          </form>
        </Card>

        <Card title="GitHub 加速源" pad>
          <p className="text-sm text-muted mb-4">
            外部表情仓库都从 GitHub 拉取。配置加速源后，请求地址会变成
            「加速源 + 原地址」，例如{' '}
            <code className="mono">https://加速源/https://github.com/owner/repo</code>。
            加速源不可用时会自动退回直连，不会导致同步失败。这里设置的是全局默认值，
            单个仓库可以在「外部仓库」页面里单独覆盖；自建加速源直接填在下面即可，
            只保存在本机配置里。
          </p>
          {proxyError && <Alert kind="error">{proxyError}</Alert>}
          <form onSubmit={saveProxy}>
            <ProxyPicker
              value={proxyDraft}
              onChange={setProxyDraft}
              presets={proxyPresets}
              testIdentifier="MemeCrafters/meme-generator-contrib"
              disabled={savingProxy}
            />
            <div className="btn-row">
              <button className="btn btn-primary" type="submit" disabled={savingProxy}>
                {savingProxy ? <span className="spinner" /> : <IconCheck size={14} />}
                保存
              </button>
              {proxyDraft.trim().replace(/\/+$/, '') !== globalProxy && (
                <button
                  className="btn"
                  type="button"
                  disabled={savingProxy}
                  onClick={() => setProxyDraft(globalProxy)}
                >
                  撤销
                </button>
              )}
            </div>
            <span className="field-hint">
              当前生效：
              {globalProxy ? <code className="mono">{globalProxy}</code> : '直连 GitHub'}
            </span>
          </form>
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
