import { useEffect, useState } from 'react'

import { ApiError, api, type Health, type UpdateResult } from '../api'
import { Alert, Badge, Empty, Spinner, sourceLabel } from '../components/ui'

export default function DashboardPage({
  health,
  onNavigate,
}: {
  health: Health | null
  onNavigate: (tab: string) => void
}) {
  const [updates, setUpdates] = useState<UpdateResult[] | null>(null)
  const [repos, setRepos] = useState<{ identifier: string }[]>([])
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
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '检查更新失败')
    } finally {
      setChecking(false)
    }
  }

  const pending = updates?.filter((r) => r.has_update).length ?? 0

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">概览</h1>
        <p className="page-desc">
          表情包生成服务的管理面板。可以在这里管理表情、同步外部仓库并检查更新。
        </p>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      {health ? (
        <div className="stats">
          <div className="stat">
            <div className="stat-label">服务版本</div>
            <div className="stat-value small">{health.version}</div>
          </div>
          <div className="stat">
            <div className="stat-label">已加载表情</div>
            <div className="stat-value">{health.memes}</div>
          </div>
          <div className="stat">
            <div className="stat-label">已封禁表情</div>
            <div className="stat-value" style={{ color: health.disabled ? 'var(--warning)' : undefined }}>
              {health.disabled}
            </div>
          </div>
          <div className="stat">
            <div className="stat-label">外部仓库</div>
            <div className="stat-value">{health.repos}</div>
          </div>
        </div>
      ) : (
        <Spinner />
      )}

      <div className="card" style={{ marginTop: 14 }}>
        <h2 className="card-title">快捷操作</h2>
        <div className="btn-row">
          <button className="btn btn-primary" onClick={() => onNavigate('memes')}>
            管理表情
          </button>
          <button className="btn" onClick={() => onNavigate('repos')}>
            添加外部仓库
          </button>
          <button className="btn" onClick={() => void checkAll()} disabled={checking}>
            {checking && <span className="spinner" />}
            检查所有更新
          </button>
        </div>
      </div>

      {updates && (
        <div className="card">
          <h2 className="card-title">
            更新检查结果
            {pending > 0 ? (
              <Badge tone="warn">{pending} 个仓库有更新</Badge>
            ) : (
              <Badge tone="on">全部最新</Badge>
            )}
          </h2>

          {updates.length === 0 && <Empty>还没有注册任何外部仓库</Empty>}

          <div className="user-list">
            {updates.map((result) => (
              <div key={result.identifier} className="row-card">
                <div className="row-head">
                  <div>
                    <div className="row-title">{sourceLabel(`repo:${result.identifier}`)}</div>
                    <div className="row-sub">
                      {result.error
                        ? `检查失败：${result.error}`
                        : result.has_update
                          ? `新增 ${result.changes.added.length} 个文件 · 修改 ${result.changes.modified.length} 个 · 删除 ${result.changes.removed.length} 个`
                          : '没有变化'}
                    </div>
                  </div>
                  {result.has_update ? (
                    <Badge tone="warn">有更新</Badge>
                  ) : (
                    <Badge tone="on">最新</Badge>
                  )}
                </div>

                {result.has_update && (
                  <div className="row-sub" style={{ marginTop: 8 }}>
                    {result.changes.added_memes.length > 0 && (
                      <div>
                        新增表情：
                        {result.changes.added_memes.map((k) => (
                          <Badge key={k} tone="info">
                            {k}
                          </Badge>
                        ))}
                      </div>
                    )}
                    {result.changes.modified_memes.length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        更新表情：
                        {result.changes.modified_memes.map((k) => (
                          <Badge key={k} tone="warn">
                            {k}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          {repos.length > 0 && (
            <div className="btn-row" style={{ marginTop: 12 }}>
              <button className="btn btn-sm" onClick={() => onNavigate('updates')}>
                查看详细变更
              </button>
            </div>
          )}
        </div>
      )}
    </>
  )
}
