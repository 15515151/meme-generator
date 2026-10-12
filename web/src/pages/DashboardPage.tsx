import { useEffect, useState } from 'react'

import { ApiError, api, type RepoInfo, type UpdateResult } from '../api'
import { Alert, Badge, Card, Empty, StatCard, relativeTime } from '../components/ui'
import { IconRepo, IconUpdate, IconMeme, IconServer, IconPlus } from '../components/icons'

export default function DashboardPage({
  health,
  onNavigate,
  pendingUpdates,
  onUpdatesChecked,
}: {
  health: { version: string; memes: number; disabled: number; repos: number } | null
  onNavigate: (tab: string) => void
  pendingUpdates: number | null
  onUpdatesChecked: (count: number) => void
}) {
  const [repos, setRepos] = useState<RepoInfo[]>([])
  const [updates, setUpdates] = useState<UpdateResult[] | null>(null)
  const [error, setError] = useState('')
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .listRepos()
      .then((result) => {
        if (!cancelled) setRepos(result.items)
      })
      .catch((e) => {
        if (!cancelled && e instanceof ApiError) setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function checkAll() {
    setChecking(true)
    setError('')
    try {
      const result = await api.checkUpdates()
      setUpdates(result.results)
      onUpdatesChecked(result.updated)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '检查更新失败')
    } finally {
      setChecking(false)
    }
  }

  const changedRepos = (updates ?? []).filter((r) => r.has_update)

  return (
    <>
      {error && <Alert kind="error">{error}</Alert>}

      <div className="stats-grid">
        <StatCard
          label="已加载表情"
          value={health?.memes ?? '—'}
          icon={<IconMeme size={16} />}
          hint={
            health
              ? health.disabled > 0
                ? `其中 ${health.disabled} 个已封禁`
                : '全部启用中'
              : undefined
          }
        />
        <StatCard
          label="外部仓库"
          value={health?.repos ?? '—'}
          icon={<IconRepo size={16} />}
          hint={repos.length > 0 ? `共 ${repos.reduce((sum, r) => sum + r.meme_count, 0)} 个外部表情` : '尚未添加'}
        />
        <StatCard
          label="已封禁"
          value={health?.disabled ?? '—'}
          icon={<IconServer size={16} />}
          tone={health?.disabled ? 'warn' : undefined}
          hint="不会出现在对外接口中"
        />
        <StatCard
          label="待同步更新"
          value={pendingUpdates === null ? '—' : pendingUpdates}
          icon={<IconUpdate size={16} />}
          tone={pendingUpdates ? 'warn' : 'ok'}
          hint={pendingUpdates ? '有仓库内容发生变化' : '全部为最新'}
        />
      </div>

      <div className="section">
        <Card
          title="快捷操作"
          actions={
            <>
              <button className="btn btn-sm" onClick={() => onNavigate('memes')}>
                <IconMeme size={14} />
                管理表情
              </button>
              <button className="btn btn-sm" onClick={() => onNavigate('repos')}>
                <IconPlus size={14} />
                添加仓库
              </button>
              <button className="btn btn-sm btn-primary" onClick={() => void checkAll()} disabled={checking}>
                {checking ? <span className="spinner" /> : <IconUpdate size={14} />}
                检查所有更新
              </button>
            </>
          }
          pad
        >
          <p className="text-muted text-sm mb-0">
            服务版本 <span className="mono">{health?.version ?? '—'}</span>
            {repos.length > 0 && <> · 已注册 {repos.length} 个外部仓库</>}
            。外部仓库的表情会在服务启动时自动加载，修改后无需重启。
          </p>
        </Card>
      </div>

      {updates && (
        <div className="section">
          <Card
            title="更新检查结果"
            count={updates.length > 0 ? `（${changedRepos.length}/${updates.length} 个仓库有更新）` : undefined}
            actions={
              changedRepos.length > 0 ? (
                <button className="btn btn-sm" onClick={() => onNavigate('updates')}>
                  查看详细变更
                </button>
              ) : undefined
            }
          >
            {updates.length === 0 ? (
              <Empty
                icon={<IconRepo size={26} />}
                title="还没有注册外部仓库"
                desc="添加仓库后可以在这里检查更新"
                action={
                  <button className="btn btn-primary btn-sm" onClick={() => onNavigate('repos')}>
                    去添加仓库
                  </button>
                }
              />
            ) : (
              <div className="list">
                {updates.map((result) => (
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
                        ) : result.has_update ? (
                          <>
                            <span>新增 {result.changes.added.length} 个文件</span>
                            <span>修改 {result.changes.modified.length} 个</span>
                            {result.changes.removed.length > 0 && (
                              <span>删除 {result.changes.removed.length} 个</span>
                            )}
                          </>
                        ) : (
                          <span>没有检测到变化</span>
                        )}
                      </div>
                      {result.has_update &&
                        (result.changes.added_memes.length > 0 ||
                          result.changes.modified_memes.length > 0) && (
                          <div className="chip-list">
                            {result.changes.added_memes.slice(0, 6).map((key) => (
                              <Badge key={`a-${key}`} tone="info">
                                +{key}
                              </Badge>
                            ))}
                            {result.changes.modified_memes.slice(0, 6).map((key) => (
                              <Badge key={`m-${key}`} tone="warn">
                                ~{key}
                              </Badge>
                            ))}
                            {result.changes.added_memes.length + result.changes.modified_memes.length > 12 && (
                              <span>等{result.changes.added_memes.length + result.changes.modified_memes.length} 个</span>
                            )}
                          </div>
                        )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      {repos.length > 0 && !updates && (
        <div className="section">
          <Card title="已注册仓库" count={`（${repos.length}）`}>
            <div className="list">
              {repos.slice(0, 5).map((repo) => (
                <div key={repo.identifier} className="list-row">
                  <div className="list-main">
                    <div className="list-title">
                      {repo.display_name}
                      <Badge tone="info">{repo.meme_count} 表情</Badge>
                    </div>
                    <div className="list-meta">
                      <span className="mono">{repo.identifier}</span>
                      <span>@{repo.ref}</span>
                      {repo.meme_dir && <span>目录 {repo.meme_dir}/</span>}
                      <span>更新于 {relativeTime(repo.updated_at)}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </>
  )
}
