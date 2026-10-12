import { useCallback, useEffect, useState } from 'react'

import { ApiError, api, type MemeUpdateItem, type UpdateResult } from '../api'
import { useToast } from '../components/Toast'
import { Alert, Badge, Empty, Modal, Spinner, sourceLabel } from '../components/ui'

export default function UpdatesPage() {
  const toast = useToast()
  const [results, setResults] = useState<UpdateResult[]>([])
  const [memeItems, setMemeItems] = useState<MemeUpdateItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [detail, setDetail] = useState<{ repo: string; file: UpdateFileView } | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [all, memes] = await Promise.all([api.checkUpdates(), api.memeUpdates()])
      setResults(all.results)
      setMemeItems(memes.items)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '检查更新失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function applyUpdate(identifier: string) {
    setBusy(identifier)
    try {
      const result = await api.updateRepo(identifier, true)
      if (result.has_update) {
        toast.success('更新已应用')
      } else {
        toast.success('已是最新，无需更新')
      }
      await load()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '更新失败')
    } finally {
      setBusy('')
    }
  }

  const updatedRepos = results.filter((r) => r.has_update)

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">更新检查</h1>
        <p className="page-desc">
          对比本地已同步内容与仓库最新状态，列出新增和修改的文件。
          下游服务也可以通过公开接口 <code className="mono">GET /api/updates</code> 获取同样的信息。
        </p>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      <div className="btn-row" style={{ marginBottom: 16 }}>
        <button className="btn btn-primary" onClick={() => void load()} disabled={loading}>
          {loading && <span className="spinner" />}
          重新检查
        </button>
      </div>

      {loading && results.length === 0 ? (
        <Spinner label="正在检查更新…" />
      ) : results.length === 0 ? (
        <Empty>还没有注册任何外部仓库，先去「仓库」页面添加一个</Empty>
      ) : (
        <>
          <div className="card">
            <h2 className="card-title">
              按表情汇总
              {memeItems.length > 0 ? (
                <Badge tone="warn">{memeItems.length} 个表情待同步</Badge>
              ) : (
                <Badge tone="on">全部最新</Badge>
              )}
            </h2>

            {memeItems.length === 0 ? (
              <div className="row-sub">没有检测到表情级别的变更</div>
            ) : (
              <div className="user-list">
                {memeItems.map((item) => (
                  <div key={`${item.repo}-${item.meme_key}`} className="row-card">
                    <div className="row-head">
                      <div style={{ minWidth: 0 }}>
                        <div className="row-title">
                          {item.meme_key}{' '}
                          <Badge tone={item.status === 'new' ? 'info' : item.status === 'removed' ? 'off' : 'warn'}>
                            {item.status === 'new' ? '新增' : item.status === 'removed' ? '已删除' : '有变更'}
                          </Badge>{' '}
                          {item.installed && <Badge tone="on">已安装</Badge>}
                        </div>
                        <div className="row-sub">
                          来自 {sourceLabel(`repo:${item.repo}`)} · {item.file_count} 个文件
                          {item.code_files > 0 && `（${item.code_files} 个代码文件）`}
                        </div>
                      </div>
                    </div>

                    {item.files.length > 0 && (
                      <div className="btn-row" style={{ marginTop: 10 }}>
                        {item.files.map((file) => (
                          <button
                            key={file.path}
                            className="btn btn-sm"
                            onClick={() =>
                              setDetail({
                                repo: item.repo,
                                file: {
                                  path: file.path,
                                  status: file.status,
                                  kind: file.kind,
                                  content: file.content ?? null,
                                  previous_content: file.previous_content ?? null,
                                },
                              })
                            }
                          >
                            查看 {file.kind === 'code' ? '代码' : '资源'}：{file.path.split('/').pop()}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <h2 className="card-title">按仓库</h2>
            <div className="user-list">
              {results.map((result) => (
                <div key={result.identifier} className="row-card">
                  <div className="row-head">
                    <div style={{ minWidth: 0 }}>
                      <div className="row-title">{sourceLabel(`repo:${result.identifier}`)}</div>
                      <div className="row-sub">
                        {result.error
                          ? `检查失败：${result.error}`
                          : `新增 ${result.changes.added.length} · 修改 ${result.changes.modified.length} · 删除 ${result.changes.removed.length}`}
                      </div>
                    </div>
                    {result.has_update ? <Badge tone="warn">有更新</Badge> : <Badge tone="on">最新</Badge>}
                  </div>

                  {result.has_update && (
                    <div className="btn-row" style={{ marginTop: 12 }}>
                      <button
                        className="btn btn-sm btn-primary"
                        disabled={busy === result.identifier}
                        onClick={() => void applyUpdate(result.identifier)}
                      >
                        {busy === result.identifier && <span className="spinner" />}
                        应用更新
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {updatedRepos.length > 0 && (
            <Alert kind="info">
              应用更新后新的表情会立即加载，无需重启服务。
            </Alert>
          )}
        </>
      )}
      {detail && (
        <CodeModal repo={detail.repo} file={detail.file} onClose={() => setDetail(null)} />
      )}
    </>
  )
}

interface UpdateFileView {
  path: string
  status: string
  kind: string
  content: string | null
  previous_content: string | null
}

function CodeModal({ repo, file, onClose }: { repo: string; file: UpdateFileView; onClose: () => void }) {
  const [showPrevious, setShowPrevious] = useState(false)

  return (
    <Modal
      title={file.path}
      onClose={onClose}
      footer={
        <button className="btn" onClick={onClose}>
          关闭
        </button>
      }
    >
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        <Badge tone={file.status === 'added' ? 'info' : 'warn'}>
          {file.status === 'added' ? '新增文件' : '修改文件'}
        </Badge>
        <Badge tone="info">{sourceLabel(`repo:${repo}`)}</Badge>
        <Badge>{file.kind === 'code' ? '代码' : '资源'}</Badge>
      </div>

      {file.content === null ? (
        <Alert kind="warn">该文件内容无法展示（可能是二进制资源或读取失败）</Alert>
      ) : (
        <>
          {file.previous_content !== null && (
            <div style={{ marginBottom: 12 }}>
              <button className="btn btn-sm" onClick={() => setShowPrevious((v) => !v)}>
                {showPrevious ? '查看新内容' : '对比修改前内容'}
              </button>
            </div>
          )}
          <pre className="code-block">
            {showPrevious && file.previous_content !== null ? file.previous_content : file.content}
          </pre>
        </>
      )}
    </Modal>
  )
}
