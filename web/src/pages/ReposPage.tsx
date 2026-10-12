import { useCallback, useEffect, useState } from 'react'

import { ApiError, api, type RepoInfo, type RepoPreset, type RepoPreview } from '../api'
import { useToast } from '../components/Toast'
import { Alert, Badge, Card, Empty, Modal, Spinner, relativeTime } from '../components/ui'
import { IconDownload, IconPlus, IconRefresh, IconRepo, IconTrash } from '../components/icons'

export default function ReposPage({ onChanged }: { onChanged?: () => void }) {
  const toast = useToast()
  const [repos, setRepos] = useState<RepoInfo[]>([])
  const [presets, setPresets] = useState<RepoPreset[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [showAdd, setShowAdd] = useState<RepoPreset | null | undefined>(undefined)
  const [expanded, setExpanded] = useState<string>('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [repoResult, presetResult] = await Promise.all([api.listRepos(), api.listPresets()])
      setRepos(repoResult.items)
      setPresets(presetResult.items)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '加载仓库列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function install(url: string, ref: string, name: string, memeDir: string) {
    setBusy(url)
    try {
      const repo = await api.addRepo(url, ref, name, memeDir)
      toast.success(`已添加「${repo.display_name}」，共 ${repo.meme_count} 个表情`)
      setShowAdd(undefined)
      await load()
      onChanged?.()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '添加仓库失败')
    } finally {
      setBusy('')
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
                      onClick={() => void install(preset.url, preset.branch, preset.name, '')}
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
          onClose={() => setShowAdd(undefined)}
          onSubmit={install}
        />
      )}
    </>
  )
}

function AddRepoModal({
  preset,
  busy,
  onClose,
  onSubmit,
}: {
  preset: RepoPreset | null
  busy: boolean
  onClose: () => void
  onSubmit: (url: string, ref: string, name: string, memeDir: string) => Promise<void>
}) {
  const [url, setUrl] = useState(preset?.url ?? '')
  const [ref, setRef] = useState(preset?.branch ?? '')
  const [name, setName] = useState(preset?.name ?? '')
  const [memeDir, setMemeDir] = useState('')
  const [preview, setPreview] = useState<RepoPreview | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [previewError, setPreviewError] = useState('')

  async function doPreview() {
    if (!url.trim()) return
    setPreviewing(true)
    setPreviewError('')
    setPreview(null)
    try {
      const result = await api.previewRepo(url.trim(), ref.trim())
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
            onClick={() => void onSubmit(url.trim(), ref.trim(), name.trim(), memeDir.trim())}
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
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://github.com/owner/repo 或 owner/repo"
          autoFocus
        />
        <span className="field-hint">
          也支持本地目录的绝对路径，服务会直接读取该目录，适合本地开发。
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

      {previewError && <Alert kind="error">{previewError}</Alert>}

      {preview && (
        <Alert kind="success">
          <div style={{ fontWeight: 600, marginBottom: 6 }}>
            探测成功：识别到 {preview.meme_count} 个表情
          </div>
          <div className="text-sm">
            分支 <code className="mono">{preview.ref}</code> · 表情目录{' '}
            <code className="mono">{preview.meme_dir || '（根目录）'}</code> · 共 {preview.file_count} 个文件
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
      </Alert>
    </Modal>
  )
}
