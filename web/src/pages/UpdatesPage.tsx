import { useCallback, useEffect, useState } from 'react'

import { ApiError, api, type MemeUpdateItem, type UpdateResult } from '../api'
import { useToast } from '../components/Toast'
import { Alert, Badge, Card, Empty, Modal, Segmented, Spinner } from '../components/ui'
import { IconCheck, IconCode, IconDownload, IconRefresh, IconRepo } from '../components/icons'

interface UpdateFileView {
  path: string
  status: string
  kind: string
  content: string | null
  previous_content: string | null
}

export default function UpdatesPage({
  onApplied,
  onNavigate,
}: {
  onApplied?: () => void
  onNavigate?: (tab: string) => void
}) {
  const toast = useToast()
  const [results, setResults] = useState<UpdateResult[]>([])
  const [memeItems, setMemeItems] = useState<MemeUpdateItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [view, setView] = useState<'meme' | 'repo'>('meme')
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
      toast.success(result.has_update ? '更新已应用' : '已是最新，无需更新')
      await load()
      onApplied?.()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '更新失败')
    } finally {
      setBusy('')
    }
  }

  async function applyAll() {
    const targets = results.filter((r) => r.has_update && !r.error)
    if (targets.length === 0) return
    if (!window.confirm(`确定更新全部 ${targets.length} 个有变更的仓库吗？`)) return
    let ok = 0
    for (const target of targets) {
      try {
        await api.updateRepo(target.identifier, true)
        ok += 1
      } catch {
        /* 单个失败继续处理其余仓库 */
      }
    }
    toast.success(`已更新 ${ok}/${targets.length} 个仓库`)
    await load()
    onApplied?.()
  }

  const updatedRepos = results.filter((r) => r.has_update)
  const totalChanges = updatedRepos.reduce(
    (sum, r) => sum + r.changes.added.length + r.changes.modified.length,
    0,
  )

  return (
    <>
      {error && <Alert kind="error">{error}</Alert>}

      <div className="toolbar">
        <Segmented
          value={view}
          onChange={setView}
          options={[
            { value: 'meme', label: '按表情' },
            { value: 'repo', label: '按仓库' },
          ]}
        />
        <div style={{ flex: 1 }} />
        <button className="btn" onClick={() => void load()} disabled={loading}>
          {loading ? <span className="spinner" /> : <IconRefresh size={14} />}
          重新检查
        </button>
        {updatedRepos.length > 0 && (
          <button className="btn btn-primary" onClick={() => void applyAll()} disabled={loading}>
            <IconDownload size={14} />
            更新全部（{updatedRepos.length}）
          </button>
        )}
      </div>

      {loading && results.length === 0 ? (
        <Card pad>
          <Spinner label="正在检查更新…" />
        </Card>
      ) : results.length === 0 ? (
        <Card pad>
          <Empty
            icon={<IconRepo size={26} />}
            title="还没有注册任何外部仓库"
            desc="先去仓库页面添加一个，才能检查更新"
            action={
              onNavigate ? (
                <button className="btn btn-primary btn-sm" onClick={() => onNavigate('repos')}>
                  去添加仓库
                </button>
              ) : undefined
            }
          />
        </Card>
      ) : view === 'meme' ? (
        <Card
          title="按表情汇总"
          count={
            memeItems.length > 0
              ? `（${memeItems.length} 个表情待同步）`
              : '（全部最新）'
          }
          actions={
            totalChanges > 0 ? (
              <Badge tone="warn">
                {totalChanges} 个文件变化
              </Badge>
            ) : (
              <Badge tone="on" dot>
                全部最新
              </Badge>
            )
          }
        >
          {memeItems.length === 0 ? (
            <Empty
              icon={<IconCheck size={26} />}
              title="没有检测到表情级别的变更"
              desc="所有仓库的表情都和本地一致"
            />
          ) : (
            <div className="list">
              {memeItems.map((item) => (
                <div key={`${item.repo}-${item.meme_key}`} className="list-row">
                  <div className="list-main">
                    <div className="list-title">
                      <span className="mono">{item.meme_key}</span>
                      <Badge
                        tone={
                          item.status === 'new' ? 'info' : item.status === 'removed' ? 'off' : 'warn'
                        }
                      >
                        {item.status === 'new' ? '新增' : item.status === 'removed' ? '已删除' : '有变更'}
                      </Badge>
                      {item.installed && (
                        <Badge tone="on" dot>
                          已安装
                        </Badge>
                      )}
                      {item.disabled && <Badge tone="off">已封禁</Badge>}
                    </div>
                    <div className="list-meta">
                      <span>来自 {item.repo}</span>
                      <span>{item.file_count} 个文件</span>
                      {item.code_files > 0 && <span>{item.code_files} 个代码文件</span>}
                    </div>

                    {item.files.length > 0 && (
                      <div className="btn-row mt-2">
                        {item.files.slice(0, 6).map((file) => (
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
                            <IconCode size={12} />
                            {file.path.split('/').pop()}
                          </button>
                        ))}
                        {item.files.length > 6 && (
                          <span className="text-sm text-dim">等 {item.files.length} 个文件</span>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      ) : (
        <Card title="按仓库" count={`（${results.length}）`}>
          <div className="list">
            {results.map((result) => (
              <div key={result.identifier} className="list-row">
                <div className="list-main">
                  <div className="list-title">
                    {result.name || result.identifier}
                    {result.error ? (
                      <Badge tone="off">检查失败</Badge>
                    ) : result.has_update ? (
                      <Badge tone="warn" dot>
                        有更新
                      </Badge>
                    ) : (
                      <Badge tone="on" dot>
                        最新
                      </Badge>
                    )}
                  </div>
                  <div className="list-meta">
                    {result.error ? (
                      <span>{result.error}</span>
                    ) : (
                      <>
                        <span>新增 {result.changes.added.length}</span>
                        <span>修改 {result.changes.modified.length}</span>
                        <span>删除 {result.changes.removed.length}</span>
                      </>
                    )}
                  </div>
                </div>

                {result.has_update && (
                  <div className="list-actions">
                    <button
                      className="btn btn-sm btn-primary"
                      disabled={busy === result.identifier}
                      onClick={() => void applyUpdate(result.identifier)}
                    >
                      {busy === result.identifier ? <span className="spinner" /> : <IconDownload size={13} />}
                      应用更新
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {updatedRepos.length > 0 && (
        <Alert kind="info">
          应用更新后新增的表情会立即加载，无需重启服务。已封禁的表情会保持封禁状态。
        </Alert>
      )}

      {detail && (
        <CodeModal repo={detail.repo} file={detail.file} onClose={() => setDetail(null)} />
      )}
    </>
  )
}

function CodeModal({ repo, file, onClose }: { repo: string; file: UpdateFileView; onClose: () => void }) {
  const [showPrevious, setShowPrevious] = useState(false)
  const hasPrevious = file.previous_content !== null && file.previous_content !== undefined

  return (
    <Modal
      title={file.path}
      onClose={onClose}
      wide
      footer={
        <button className="btn" onClick={onClose}>
          关闭
        </button>
      }
    >
      <div className="row mb-4">
        <Badge tone={file.status === 'added' ? 'info' : 'warn'}>
          {file.status === 'added' ? '新增文件' : '修改文件'}
        </Badge>
        <Badge>{repo}</Badge>
        <Badge>{file.kind === 'code' ? '代码' : '资源'}</Badge>
      </div>

      {file.content === null ? (
        <Alert kind="warn">该文件内容无法展示（可能是二进制资源或读取失败）</Alert>
      ) : (
        <>
          {hasPrevious && (
            <div className="row mb-3">
              <Segmented
                value={showPrevious ? 'old' : 'new'}
                onChange={(next) => setShowPrevious(next === 'old')}
                options={[
                  { value: 'new', label: '新内容' },
                  { value: 'old', label: '修改前' },
                ]}
              />
            </div>
          )}
          <pre className="code-block">
            {showPrevious && hasPrevious ? file.previous_content : file.content}
          </pre>
        </>
      )}
    </Modal>
  )
}
