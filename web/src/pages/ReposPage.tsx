import { useCallback, useEffect, useState } from 'react'

import { ApiError, api, type RepoInfo } from '../api'
import { useToast } from '../components/Toast'
import { Alert, Badge, Empty, Modal, Spinner, sourceLabel } from '../components/ui'

const SUGGESTED = [
  {
    url: 'https://github.com/MemeCrafters/meme-generator-contrib',
    desc: 'meme-generator 官方额外表情仓库',
  },
  {
    url: 'https://github.com/anyliew/meme_emoji',
    desc: '更多热门表情包模板',
  },
]

export default function ReposPage() {
  const toast = useToast()
  const [repos, setRepos] = useState<RepoInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [adding, setAdding] = useState(false)
  const [busy, setBusy] = useState('')
  const [showAdd, setShowAdd] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.listRepos()
      setRepos(result.items)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '加载仓库列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function addRepo(url: string, ref: string) {
    setAdding(true)
    try {
      const repo = await api.addRepo(url, ref)
      toast.success(`已添加仓库，共 ${repo.meme_count} 个表情`)
      setShowAdd(false)
      await load()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '添加仓库失败')
    } finally {
      setAdding(false)
    }
  }

  async function removeRepo(repo: RepoInfo) {
    if (!window.confirm(`确定移除仓库「${repo.identifier}」吗？它会卸载该仓库带来的 ${repo.meme_count} 个表情。`))
      return
    setBusy(repo.identifier)
    try {
      const result = await api.removeRepo(repo.identifier)
      toast.success(result.message)
      await load()
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
      if (result.applied && result.has_update) {
        toast.success(
          `已更新：新增 ${result.changes?.added.length ?? 0} 个文件，修改 ${result.changes?.modified.length ?? 0} 个`,
        )
      } else {
        toast.success('仓库已是最新')
      }
      await load()
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

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">外部表情仓库</h1>
        <p className="page-desc">
          添加第三方表情仓库后，服务会下载其中的表情并在启动时加载。
          支持 GitHub 地址（<code className="mono">owner/repo</code>）与本地绝对路径。
        </p>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      <div className="btn-row" style={{ marginBottom: 16 }}>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>
          添加仓库
        </button>
        <button className="btn" onClick={() => void load()}>
          刷新
        </button>
      </div>

      {loading ? (
        <Spinner />
      ) : repos.length === 0 ? (
        <Empty>还没有添加任何外部仓库</Empty>
      ) : (
        <div className="user-list">
          {repos.map((repo) => (
            <div key={repo.identifier} className="row-card">
              <div className="row-head">
                <div style={{ minWidth: 0 }}>
                  <div className="row-title">{sourceLabel(`repo:${repo.identifier}`)}</div>
                  <div className="row-sub">
                    {repo.meme_count} 个表情 · {repo.file_count} 个文件 · 分支 {repo.ref}
                    {repo.updated_at && (
                      <> · 更新于 {new Date(repo.updated_at * 1000).toLocaleString()}</>
                    )}
                  </div>
                </div>
                <Badge tone="info">{repo.meme_count} 表情</Badge>
              </div>

              {repo.meme_keys.length > 0 && (
                <div className="row-sub" style={{ marginTop: 8 }}>
                  包含：
                  {repo.meme_keys.slice(0, 12).map((key) => (
                    <Badge key={key}>{key}</Badge>
                  ))}
                  {repo.meme_keys.length > 12 && (
                    <span> 等 {repo.meme_keys.length} 个</span>
                  )}
                </div>
              )}

              <div className="btn-row" style={{ marginTop: 12 }}>
                <button
                  className="btn btn-sm"
                  disabled={busy === repo.identifier}
                  onClick={() => void updateRepo(repo)}
                >
                  {busy === repo.identifier && <span className="spinner" />}
                  更新
                </button>
                <button
                  className="btn btn-sm"
                  disabled={busy === repo.identifier}
                  onClick={() => void reloadRepo(repo)}
                >
                  重新加载
                </button>
                <button
                  className="btn btn-sm btn-danger"
                  disabled={busy === repo.identifier}
                  onClick={() => void removeRepo(repo)}
                >
                  移除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showAdd && (
        <AddRepoModal onClose={() => setShowAdd(false)} onSubmit={addRepo} busy={adding} />
      )}
    </>
  )
}

function AddRepoModal({
  onClose,
  onSubmit,
  busy,
}: {
  onClose: () => void
  onSubmit: (url: string, ref: string) => Promise<void>
  busy: boolean
}) {
  const [url, setUrl] = useState('')
  const [ref, setRef] = useState('main')

  return (
    <Modal
      title="添加外部仓库"
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose} disabled={busy}>
            取消
          </button>
          <button
            className="btn btn-primary"
            disabled={busy || !url.trim()}
            onClick={() => void onSubmit(url.trim(), ref.trim() || 'main')}
          >
            {busy && <span className="spinner" />}
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
      </div>

      <div className="field">
        <label htmlFor="repo-ref">分支 / 标签 / 提交</label>
        <input
          id="repo-ref"
          className="input"
          value={ref}
          onChange={(e) => setRef(e.target.value)}
          placeholder="main"
        />
      </div>

      <Alert kind="info">
        也可以填写本地目录的绝对路径，服务会直接从该目录读取表情，适合本地开发。
        私有仓库可通过启动服务前设置 <code className="mono">GITHUB_TOKEN</code> 环境变量来访问。
      </Alert>

      <div className="card-title" style={{ fontSize: 13, marginTop: 16 }}>
        常用仓库
      </div>
      <div className="btn-row">
        {SUGGESTED.map((item) => (
          <button
            key={item.url}
            className="btn btn-sm"
            onClick={() => setUrl(item.url)}
            title={item.desc}
          >
            {item.url.replace('https://github.com/', '')}
          </button>
        ))}
      </div>
    </Modal>
  )
}
