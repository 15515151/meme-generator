import { useCallback, useEffect, useState } from 'react'

import {
  ApiError,
  api,
  type ProxyPresets,
  type RepoInfo,
  type RepoPreset,
  type RepoPreview,
} from '../api'
import { useToast } from '../components/Toast'
import { Alert, Badge, Card, Empty, Modal, Spinner, relativeTime } from '../components/ui'
import { ProxyPicker } from '../components/ProxyPicker'
import {
  IconCheck,
  IconDownload,
  IconPlus,
  IconRefresh,
  IconRepo,
  IconTrash,
  IconZap,
} from '../components/icons'

export default function ReposPage({ onChanged }: { onChanged?: () => void }) {
  const toast = useToast()
  const [repos, setRepos] = useState<RepoInfo[]>([])
  const [presets, setPresets] = useState<RepoPreset[]>([])
  const [proxies, setProxies] = useState<ProxyPresets>({ default: '', items: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [showAdd, setShowAdd] = useState<RepoPreset | null | undefined>(undefined)
  const [proxyTarget, setProxyTarget] = useState<RepoInfo | null>(null)
  const [showGlobalProxy, setShowGlobalProxy] = useState(false)
  const [expanded, setExpanded] = useState<string>('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [repoResult, presetResult, proxyResult] = await Promise.all([
        api.listRepos(),
        api.listPresets(),
        api.listProxies(),
      ])
      setRepos(repoResult.items)
      setPresets(presetResult.items)
      setProxies(proxyResult)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '加载仓库列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function install(url: string, ref: string, name: string, memeDir: string, proxy: string) {
    setBusy(url)
    try {
      const repo = await api.addRepo(url, ref, name, memeDir, proxy)
      const via = repo.effective_proxy ? `，加速源 ${repo.effective_proxy}` : ''
      toast.success(`已添加「${repo.display_name}」，共 ${repo.meme_count} 个表情${via}`)
      setShowAdd(undefined)
      await load()
      onChanged?.()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '添加仓库失败')
    } finally {
      setBusy('')
    }
  }

  async function saveProxy(repo: RepoInfo, proxy: string, apply: boolean) {
    try {
      const result = await api.setRepoSettings(repo.identifier, { proxy, apply })
      const via = result.effective_proxy ? `加速源 ${result.effective_proxy}` : '直连'
      toast.success(apply ? `已按新加速源重新拉取（${via}）` : `已保存：${via}`)
      setProxyTarget(null)
      await load()
      onChanged?.()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '保存加速源失败')
    }
  }

  async function saveGlobalProxy(proxy: string) {
    try {
      const result = await api.updateSettings({ github_proxy: proxy.trim() })
      const via = result.repo.effective_proxy
      toast.success(via ? `全局加速源已设置为 ${via}` : '已改为直连 GitHub')
      setShowGlobalProxy(false)
      await load()
      onChanged?.()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '保存全局加速源失败')
    }
  }

  async function removeRepo(repo: RepoInfo) {
    if (
      !window.confirm(
        `确定移除「${repo.display_name}」吗？它会卸载该仓库带来的 ${repo.meme_count} 个表情。`,
      )
    )
      return
    setBusy(repo.identifier)
    try {
      const result = await api.removeRepo(repo.identifier)
      toast.success(result.message)
      await load()
      onChanged?.()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '移除失败')
    } finally {
      setBusy('')
    }
  }

  async function updateRepo(repo: RepoInfo) {
    setBusy(repo.identifier)
    try {
      const result = await api.updateRepo(repo.identifier, true)
      if (result.has_update) {
        toast.success(
          `已更新：新增 ${result.changes?.added.length ?? 0} 个文件，修改 ${result.changes?.modified.length ?? 0} 个`,
        )
      } else {
        toast.success('仓库已是最新')
      }
      await load()
      onChanged?.()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '更新失败')
    } finally {
      setBusy('')
    }
  }

  async function reloadRepo(repo: RepoInfo) {
    setBusy(repo.identifier)
    try {
      const result = await api.reloadRepo(repo.identifier)
      toast.success(result.message)
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '重新加载失败')
    } finally {
      setBusy('')
    }
  }

  const installedIds = new Set(repos.map((r) => r.identifier))
  const availablePresets = presets.filter((p) => !p.installed && !installedIds.has(p.identifier))

  return (
    <>
      {error && <Alert kind="error">{error}</Alert>}

      <div className="section" style={{ marginTop: 0 }}>
        <div className="proxy-banner">
          <div className="proxy-banner-main">
            <IconZap size={17} />
            <div>
              <div style={{ fontWeight: 600 }}>GitHub 加速源</div>
              <div className="text-sm text-dim">
                {proxies.default ? (
                  <>
                    全局默认 <code className="mono">{proxies.default}</code>
                    ，所有仓库生效，可在下方为单个仓库单独覆盖
                  </>
                ) : (
                  '未设置：当前直连 GitHub。添加仓库或更新频繁失败时，可以在这里配置一个镜像前缀'
                )}
              </div>
            </div>
          </div>
          <button className="btn btn-sm" onClick={() => setShowGlobalProxy(true)}>
            <IconZap size={13} />
            设置加速源
          </button>
        </div>
      </div>

      {availablePresets.length > 0 && (
        <div className="section" style={{ marginTop: 0 }}>
          <Card
            title="常用仓库"
            count={`（${availablePresets.length} 个可添加）`}
            actions={
              <button className="btn btn-sm btn-primary" onClick={() => setShowAdd(null)}>
                <IconPlus size={14} />
                自定义添加
              </button>
            }
            pad
          >
            <div className="preset-grid">
              {availablePresets.map((preset) => (
                <div key={preset.identifier} className="preset-card">
                  <div className="preset-name">{preset.name}</div>
                  <div className="preset-url" title={preset.identifier}>
                    {preset.identifier}
                  </div>
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <Badge>@{preset.branch}</Badge>
                    <button
                      className="btn btn-sm btn-primary"
                      disabled={busy === preset.url}
                      onClick={() =>
                        void install(preset.url, preset.branch, preset.name, '', '')
                      }
                    >
                      {busy === preset.url ? <span className="spinner" /> : <IconDownload size={13} />}
                      添加
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      <div className="section">
        <Card
          title="已添加仓库"
          count={repos.length > 0 ? `（${repos.length}）` : undefined}
          actions={
            <>
              <button className="btn btn-sm" onClick={() => setShowAdd(null)}>
                <IconPlus size={14} />
                添加仓库
              </button>
              <button className="btn btn-sm btn-icon" onClick={() => void load()} title="刷新">
                <IconRefresh size={15} />
              </button>
            </>
          }
        >
          {loading ? (
            <Spinner label="加载中…" />
          ) : repos.length === 0 ? (
            <Empty
              icon={<IconRepo size={26} />}
              title="还没有添加外部仓库"
              desc="从上方常用仓库一键添加，或填自定义地址。仓库的表情会立即加载。"
            />
          ) : (
            <div className="list">
              {repos.map((repo) => {
                const isOpen = expanded === repo.identifier
                return (
                  <div key={repo.identifier} className="list-row">
                    <div className="list-main">
                      <div className="list-title">
                        {repo.display_name}
                        <Badge tone="info">{repo.meme_count} 表情</Badge>
                        <Badge tone="on" dot>
                          已加载
                        </Badge>
                      </div>

                      <div className="list-meta">
                        <span className="mono">{repo.identifier}</span>
                        <span>分支 {repo.ref}</span>
                        {repo.meme_dir && <span>表情目录 {repo.meme_dir}/</span>}
                        <span>{repo.file_count} 个文件</span>
                        <span>更新于 {relativeTime(repo.updated_at)}</span>
                      </div>

                      <div className="list-meta">
                        <IconZap size={13} />
                        {repo.effective_proxy ? (
                          <>
                            <span>加速源</span>
                            <span className="mono">{repo.effective_proxy}</span>
                            {repo.accelerated_url && (
                              <span className="mono text-dim">{repo.accelerated_url}</span>
                            )}
                          </>
                        ) : (
                          <span>直连 GitHub</span>
                        )}
                      </div>

                      {repo.meme_keys.length > 0 && (
                        <div className="chip-list">
                          {(isOpen ? repo.meme_keys : repo.meme_keys.slice(0, 10)).map((key) => (
                            <Badge key={key}>{key}</Badge>
                          ))}
                          {repo.meme_keys.length > 10 && (
                            <button
                              className="btn btn-sm btn-ghost"
                              onClick={() => setExpanded(isOpen ? '' : repo.identifier)}
                            >
                              {isOpen ? '收起' : `等 ${repo.meme_keys.length} 个`}
                            </button>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="list-actions">
                      <button
                        className="btn btn-sm"
                        disabled={busy === repo.identifier}
                        onClick={() => setProxyTarget(repo)}
                      >
                        <IconZap size={13} />
                        加速源
                      </button>
                      <button
                        className="btn btn-sm"
                        disabled={busy === repo.identifier}
                        onClick={() => void updateRepo(repo)}
                      >
                        {busy === repo.identifier ? <span className="spinner" /> : <IconDownload size={13} />}
                        更新
                      </button>
                      <button
                        className="btn btn-sm"
                        disabled={busy === repo.identifier}
                        onClick={() => void reloadRepo(repo)}
                      >
                        <IconRefresh size={13} />
                        重新加载
                      </button>
                      <button
                        className="btn btn-sm btn-danger"
                        disabled={busy === repo.identifier}
                        onClick={() => void removeRepo(repo)}
                      >
                        <IconTrash size={13} />
                        移除
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </div>

      {showAdd !== undefined && (
        <AddRepoModal
          preset={showAdd}
          busy={!!busy}
          proxies={proxies}
          onClose={() => setShowAdd(undefined)}
          onSubmit={install}
        />
      )}

      {proxyTarget && (
        <RepoProxyModal
          repo={proxyTarget}
          proxies={proxies}
          onClose={() => setProxyTarget(null)}
          onSubmit={saveProxy}
        />
      )}

      {showGlobalProxy && (
        <GlobalProxyModal
          proxies={proxies}
          onClose={() => setShowGlobalProxy(false)}
          onSubmit={saveGlobalProxy}
        />
      )}
    </>
  )
}

/** 全局默认加速源（所有没单独设置的仓库都用它）。 */
function GlobalProxyModal({
  proxies,
  onClose,
  onSubmit,
}: {
  proxies: ProxyPresets
  onClose: () => void
  onSubmit: (proxy: string) => Promise<void>
}) {
  const [proxy, setProxy] = useState(proxies.default)
  const [busy, setBusy] = useState(false)

  const trimmed = proxy.trim().replace(/\/+$/, '')
  const preview = trimmed
    ? `${trimmed}/https://github.com/owner/repo`
    : 'https://github.com/owner/repo'

  async function submit() {
    setBusy(true)
    try {
      await onSubmit(proxy)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title="GitHub 加速源（全局默认）"
      onClose={onClose}
      wide
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button className="btn btn-primary" disabled={busy} onClick={() => void submit()}>
            {busy ? <span className="spinner" /> : <IconCheck size={14} />}
            保存
          </button>
        </>
      }
    >
      <Alert kind="info">
        加速源就是加在 GitHub 地址前面的前缀，保存后请求会变成{' '}
        <code className="mono">{preview}</code>。留空表示直连 GitHub。
        自建加速源直接填在下面即可，只保存在服务端配置里，不涉及代码仓库。
      </Alert>

      <ProxyPicker
        value={proxy}
        onChange={setProxy}
        presets={proxies.items}
        testIdentifier="MemeCrafters/meme-generator-contrib"
      />

      <Alert kind="warn">
        这是全局默认值：已经单独设置过加速源的仓库不受影响，仍然使用各自的设置；
        加速源不可用时请求会自动退回直连。
      </Alert>
    </Modal>
  )
}

/** 给已添加的仓库单独设置加速源。 */
function RepoProxyModal({
  repo,
  proxies,
  onClose,
  onSubmit,
}: {
  repo: RepoInfo
  proxies: ProxyPresets
  onClose: () => void
  onSubmit: (repo: RepoInfo, proxy: string, apply: boolean) => Promise<void>
}) {
  const [proxy, setProxy] = useState(repo.proxy)
  const [busy, setBusy] = useState(false)

  const repoUrl = `https://github.com/${repo.identifier}`
  const activeProxy = (proxy.trim() || repo.effective_proxy).replace(/\/+$/, '')
  const effectiveUrl = activeProxy ? `${activeProxy}/${repoUrl}` : repoUrl

  async function submit(apply: boolean) {
    setBusy(true)
    try {
      await onSubmit(repo, proxy.trim(), apply)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={`加速源 · ${repo.display_name}`}
      onClose={onClose}
      wide
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button className="btn" disabled={busy} onClick={() => void submit(false)}>
            <IconCheck size={14} />
            仅保存
          </button>
          <button className="btn btn-primary" disabled={busy} onClick={() => void submit(true)}>
            {busy ? <span className="spinner" /> : <IconDownload size={14} />}
            保存并重新拉取
          </button>
        </>
      }
    >
      <Alert kind="info">
        加速源就是加在 GitHub 地址前面的前缀，当前会以{' '}
        <code className="mono">{effectiveUrl}</code> 的形式访问
        {activeProxy ? '' : '（未设置加速源，直连 GitHub）'}。加速源不可用时会自动退回直连，
        不会让仓库同步失败；自建加速源直接填在下面即可，只保存在本机配置里。
      </Alert>

      <ProxyPicker
        value={proxy}
        onChange={setProxy}
        presets={proxies.items}
        fallback={proxies.default}
        testIdentifier={repo.identifier}
        testRef={repo.ref}
      />

      <Alert kind="warn">
        「保存并重新拉取」会立刻用新的加速源同步一次仓库；仓库文件与 sha 不受加速源影响，
        换加速源不会导致表情重复下载。
      </Alert>
    </Modal>
  )
}

function AddRepoModal({
  preset,
  busy,
  proxies,
  onClose,
  onSubmit,
}: {
  preset: RepoPreset | null
  busy: boolean
  proxies: ProxyPresets
  onClose: () => void
  onSubmit: (
    url: string,
    ref: string,
    name: string,
    memeDir: string,
    proxy: string,
  ) => Promise<void>
}) {
  const [url, setUrl] = useState(preset?.url ?? '')
  const [ref, setRef] = useState(preset?.branch ?? '')
  const [name, setName] = useState(preset?.name ?? '')
  const [memeDir, setMemeDir] = useState('')
  const [proxy, setProxy] = useState('')
  const [preview, setPreview] = useState<RepoPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [previewError, setPreviewError] = useState('')

  /** 直接把「加速源 + 仓库地址」整串粘进来时自动拆开填写。 */
  function handleUrlChange(next: string) {
    const match = /\/https?:\/\//.exec(next)
    if (match && match.index > 0) {
      setUrl(next.slice(match.index + 1))
      setProxy(next.slice(0, match.index))
      return
    }
    setUrl(next)
  }

  async function doPreview() {
    if (!url.trim()) return
    setPreviewing(true)
    setPreviewError('')
    setPreview(null)
    try {
      const result = await api.previewRepo(url.trim(), ref.trim(), proxy.trim())
      setPreview(result)
      // 用探测结果补全未填写的字段
      if (!name) setName(result.name)
      if (!ref) setRef(result.ref)
    } catch (e) {
      setPreviewError(e instanceof ApiError ? e.message : '探测失败')
    } finally {
      setPreviewing(false)
    }
  }

  return (
    <Modal
      title="添加外部仓库"
      onClose={onClose}
      wide
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            className="btn"
            onClick={() => void doPreview()}
            disabled={previewing || busy || !url.trim()}
          >
            {previewing ? <span className="spinner" /> : <IconRefresh size={14} />}
            探测仓库
          </button>
          <button
            className="btn btn-primary"
            disabled={busy || !url.trim()}
            onClick={() =>
              void onSubmit(url.trim(), ref.trim(), name.trim(), memeDir.trim(), proxy.trim())
            }
          >
            {busy ? <span className="spinner" /> : <IconDownload size={14} />}
            添加并下载
          </button>
        </>
      }
    >
      <div className="field">
        <label htmlFor="repo-url">仓库地址</label>
        <input
          id="repo-url"
          className="input"
          value={url}
          onChange={(e) => handleUrlChange(e.target.value)}
          placeholder="https://github.com/owner/repo 或 owner/repo"
          autoFocus
        />
        <span className="field-hint">
          也支持本地目录的绝对路径，服务会直接读取该目录，适合本地开发。
          把「加速源 + 仓库地址」整串粘进来会自动拆成两栏。
        </span>
      </div>

      <div className="grid-2">
        <div className="field">
          <label htmlFor="repo-ref">分支 / 标签 / 提交</label>
          <input
            id="repo-ref"
            className="input"
            value={ref}
            onChange={(e) => setRef(e.target.value)}
            placeholder="留空自动探测"
          />
        </div>
        <div className="field">
          <label htmlFor="repo-name">显示名称</label>
          <input
            id="repo-name"
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="留空使用仓库名"
          />
        </div>
      </div>

      <div className="field">
        <label htmlFor="repo-dir">表情目录</label>
        <input
          id="repo-dir"
          className="input"
          value={memeDir}
          onChange={(e) => setMemeDir(e.target.value)}
          placeholder="留空自动探测（memes/ 或 emoji/）"
        />
        <span className="field-hint">
          不同仓库的约定不一样，有的用 <code className="mono">memes/</code>，有的用{' '}
          <code className="mono">emoji/</code>。点「探测仓库」可自动识别。
        </span>
      </div>

      <ProxyPicker
        value={proxy}
        onChange={setProxy}
        presets={proxies.items}
        fallback={proxies.default}
        testIdentifier={url.trim()}
        testRef={ref.trim()}
      />

      {previewError && <Alert kind="error">{previewError}</Alert>}

      {preview && (
        <Alert kind="success">
          <div style={{ fontWeight: 600, marginBottom: 6 }}>
            探测成功：识别到 {preview.meme_count} 个表情
          </div>
          <div className="text-sm">
            分支 <code className="mono">{preview.ref}</code> · 表情目录{' '}
            <code className="mono">{preview.meme_dir || '（根目录）'}</code> · 共 {preview.file_count} 个文件
            {preview.effective_proxy && (
              <>
                {' '}
                · 加速源 <code className="mono">{preview.effective_proxy}</code>
              </>
            )}
          </div>
          <div className="chip-list mt-3">
            {preview.meme_keys.slice(0, 14).map((key) => (
              <Badge key={key}>{key}</Badge>
            ))}
            {preview.meme_keys.length > 14 && <span>等 {preview.meme_keys.length} 个</span>}
          </div>
        </Alert>
      )}

      <Alert kind="info">
        私有仓库需要在启动服务前设置 <code className="mono">GITHUB_TOKEN</code> 环境变量。
        大型仓库（几百 MB）首次下载需要一些时间，之后检查更新只用轻量的比对接口。
        访问 GitHub 困难时先选一个加速源并点「测试加速源」，确认可用再添加。
      </Alert>
    </Modal>
  )
}
