import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError, api, type MemeSummary } from '../api'
import { useToast } from '../components/Toast'
import { Alert, Badge, Empty, Modal, Spinner, sourceLabel } from '../components/ui'

type StatusFilter = 'all' | 'enabled' | 'disabled'

export default function MemesPage() {
  const toast = useToast()
  const [items, setItems] = useState<MemeSummary[]>([])
  const [sources, setSources] = useState<string[]>([])
  const [counts, setCounts] = useState({ total: 0, enabled: 0, disabled: 0 })
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [source, setSource] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<MemeSummary | null>(null)
  const [busyKey, setBusyKey] = useState('')

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true)
      setError('')
      try {
        const result = await api.listMemes({ q: query, status, source })
        if (signal?.aborted) return
        setItems(result.items)
        setSources(result.sources)
        setCounts({ total: result.total, enabled: result.enabled, disabled: result.disabled })
      } catch (e) {
        if (signal?.aborted) return
        setError(e instanceof ApiError ? e.message : '加载失败')
      } finally {
        if (!signal?.aborted) setLoading(false)
      }
    },
    [query, status, source],
  )

  // 输入时防抖，避免每敲一个字都请求
  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => void load(controller.signal), 250)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [load])

  async function toggle(meme: MemeSummary, disabled: boolean) {
    setBusyKey(meme.key)
    try {
      const result = await api.toggleMeme(meme.key, disabled)
      toast.success(result.message)
      setItems((prev) =>
        prev.map((item) => (item.key === meme.key ? { ...item, disabled } : item)),
      )
      if (status !== 'all') void load()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '操作失败')
    } finally {
      setBusyKey('')
    }
  }

  async function setAll(disabled: boolean) {
    const keys = items.map((item) => item.key)
    if (keys.length === 0) return
    const verb = disabled ? '封禁' : '启用'
    if (!window.confirm(`确定${verb}当前筛选出的 ${keys.length} 个表情吗？`)) return
    try {
      const result = await api.batchToggle(keys, disabled)
      toast.success(`已${verb} ${result.updated.length} 个表情`)
      void load()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '批量操作失败')
    }
  }

  return (
    <>
      <div className="page-head">
        <h1 className="page-title">表情管理</h1>
        <p className="page-desc">
          共 {counts.total} 个表情，已启用 {counts.enabled} 个，已封禁 {counts.disabled} 个。
          封禁后表情仍然保留，但不再出现在对外接口中。
        </p>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      <div className="toolbar">
        <input
          className="input"
          placeholder="搜索 key、关键词或标签…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          className="input"
          value={status}
          onChange={(e) => setStatus(e.target.value as StatusFilter)}
        >
          <option value="all">全部状态</option>
          <option value="enabled">已启用</option>
          <option value="disabled">已封禁</option>
        </select>
        {sources.length > 1 && (
          <select className="input" value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">全部来源</option>
            {sources.map((item) => (
              <option key={item} value={item}>
                {sourceLabel(item)}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="btn-row" style={{ marginBottom: 16 }}>
        <button className="btn btn-sm" onClick={() => void setAll(true)} disabled={!items.length}>
          封禁当前结果
        </button>
        <button className="btn btn-sm" onClick={() => void setAll(false)} disabled={!items.length}>
          启用当前结果
        </button>
        <button className="btn btn-sm" onClick={() => void load()}>
          刷新
        </button>
      </div>

      {loading && items.length === 0 ? (
        <Spinner />
      ) : items.length === 0 ? (
        <Empty>没有匹配的表情</Empty>
      ) : (
        <div className="meme-grid">
          {items.map((meme) => (
            <MemeCard
              key={meme.key}
              meme={meme}
              busy={busyKey === meme.key}
              onToggle={(disabled) => void toggle(meme, disabled)}
              onOpen={() => setSelected(meme)}
            />
          ))}
        </div>
      )}

      {selected && (
        <PreviewModal
          meme={selected}
          onClose={() => setSelected(null)}
          onToggle={(disabled) => {
            void toggle(selected, disabled)
            setSelected({ ...selected, disabled })
          }}
        />
      )}
    </>
  )
}

function MemeCard({
  meme,
  busy,
  onToggle,
  onOpen,
}: {
  meme: MemeSummary
  busy: boolean
  onToggle: (disabled: boolean) => void
  onOpen: () => void
}) {
  const [src, setSrc] = useState('')
  const [failed, setFailed] = useState(false)
  const [visible, setVisible] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const cardRef = useRef<HTMLDivElement>(null)
  const objectUrl = useRef('')

  // 预览要实际渲染图片，代价不低；滚动到视野内才生成。
  useEffect(() => {
    const node = cardRef.current
    if (!node) return
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true)
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { rootMargin: '200px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!visible) return
    let cancelled = false
    setFailed(false)
    api
      .fetchMemePreview(meme.key, '')
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url)
          return
        }
        if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
        objectUrl.current = url
        setSrc(url)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
    }
  }, [meme.key, visible, reloadKey])

  useEffect(
    () => () => {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
    },
    [],
  )

  return (
    <div ref={cardRef} className={`meme-card${meme.disabled ? ' disabled' : ''}`}>
      <div className="meme-thumb">
        {src && !failed ? (
          <img src={src} alt={meme.key} loading="lazy" />
        ) : failed ? (
          <div className="placeholder">预览生成失败</div>
        ) : (
          <span className="spinner" />
        )}
        <button
          className="refresh"
          onClick={() => setReloadKey((k) => k + 1)}
          title="重新生成预览"
        >
          刷新
        </button>
      </div>

      <div className="meme-body">
        <div className="meme-key">{meme.key}</div>
        <div className="meme-meta">
          <Badge tone={meme.disabled ? 'off' : 'on'}>{meme.disabled ? '已封禁' : '启用中'}</Badge>
          {meme.source !== 'builtin' && <Badge tone="info">{sourceLabel(meme.source)}</Badge>}
          <Badge>
            {meme.min_images > 0 ? `${meme.min_images} 图` : ''}
            {meme.min_images > 0 && meme.min_texts > 0 ? ' + ' : ''}
            {meme.min_texts > 0 ? `${meme.min_texts} 文` : ''}
            {meme.min_images === 0 && meme.min_texts === 0 ? '无参数' : ''}
          </Badge>
        </div>
        {meme.keywords.length > 0 && (
          <div className="row-sub">关键词：{meme.keywords.join('、')}</div>
        )}

        <div className="meme-actions">
          <button className="btn btn-sm" onClick={onOpen}>
            预览
          </button>
          <button
            className={`btn btn-sm ${meme.disabled ? 'btn-success' : 'btn-danger'}`}
            disabled={busy}
            onClick={() => onToggle(!meme.disabled)}
          >
            {busy ? <span className="spinner" /> : meme.disabled ? '启用' : '封禁'}
          </button>
        </div>
      </div>
    </div>
  )
}

function PreviewModal({
  meme,
  onClose,
  onToggle,
}: {
  meme: MemeSummary
  onClose: () => void
  onToggle: (disabled: boolean) => void
}) {
  const [texts, setTexts] = useState(meme.default_texts.join(','))
  const [src, setSrc] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [assets, setAssets] = useState<{ path: string; size: number; kind: string }[] | null>(null)
  const objectUrl = useRef('')

  const generate = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const url = await api.fetchMemePreview(meme.key, texts)
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
      objectUrl.current = url
      setSrc(url)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '预览生成失败')
    } finally {
      setLoading(false)
    }
  }, [meme.key, texts])

  useEffect(() => {
    void generate()
    return () => {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current)
    }
    // 仅在打开弹窗时自动生成一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meme.key])

  useEffect(() => {
    let cancelled = false
    api
      .memeAssets(meme.key)
      .then((result) => {
        if (!cancelled) setAssets(result.files)
      })
      .catch(() => {
        if (!cancelled) setAssets([])
      })
    return () => {
      cancelled = true
    }
  }, [meme.key])

  const paramText = useMemo(() => {
    const parts: string[] = []
    if (meme.min_images > 0) parts.push(`图片 ${meme.min_images}~${meme.max_images || meme.min_images} 张`)
    if (meme.min_texts > 0) parts.push(`文本 ${meme.min_texts}~${meme.max_texts || meme.min_texts} 段`)
    return parts.length ? parts.join(' · ') : '无需输入参数'
  }, [meme])

  return (
    <Modal
      title={meme.key}
      onClose={onClose}
      footer={
        <>
          <button className="btn" onClick={onClose}>
            关闭
          </button>
          <button
            className={`btn ${meme.disabled ? 'btn-success' : 'btn-danger'}`}
            onClick={() => onToggle(!meme.disabled)}
          >
            {meme.disabled ? '启用此表情' : '封禁此表情'}
          </button>
        </>
      }
    >
      <div style={{ marginBottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <Badge tone={meme.disabled ? 'off' : 'on'}>{meme.disabled ? '已封禁' : '启用中'}</Badge>
        <Badge tone="info">来源：{sourceLabel(meme.source)}</Badge>
        <Badge>{paramText}</Badge>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      <div className="preview-box">
        {loading ? <Spinner label="生成预览中…" /> : src ? <img src={src} alt={meme.key} /> : null}
        {!loading && !src && !error && (
          <div className="placeholder" style={{ color: 'var(--text-dim)', fontSize: 12 }}>
            暂无预览
          </div>
        )}
      </div>

      {meme.min_images > 0 && (
        <Alert kind="info">
          预览使用随机图片生成；实际调用时请自行上传图片。参数：图片 {meme.min_images}~
          {meme.max_images || meme.min_images} 张
          {meme.min_texts > 0 && `，文本 ${meme.min_texts}~${meme.max_texts || meme.min_texts} 段`}
        </Alert>
      )}

      {meme.min_texts > 0 && (
        <>
          <div className="field">
            <label htmlFor="preview-texts">预览文本（逗号分隔，最多 {meme.max_texts || meme.min_texts} 段）</label>
            <input
              id="preview-texts"
              className="input"
              value={texts}
              onChange={(e) => setTexts(e.target.value)}
              placeholder={meme.default_texts.join(',')}
            />
          </div>
          <button className="btn btn-primary" onClick={() => void generate()} disabled={loading}>
            {loading && <span className="spinner" />}
            重新生成
          </button>
        </>
      )}

      {meme.keywords.length > 0 && (
        <div className="row-sub" style={{ marginTop: 14 }}>
          关键词：{meme.keywords.join('、')}
        </div>
      )}

      <div className="row-sub" style={{ marginTop: 8 }}>
        创建于 {new Date(meme.date_created).toLocaleDateString()} · 修改于{' '}
        {new Date(meme.date_modified).toLocaleDateString()}
      </div>

      {assets && (
        <div style={{ marginTop: 18 }}>
          <div className="card-title" style={{ fontSize: 14 }}>
            资源文件（{assets.length}）
          </div>
          {assets.length === 0 ? (
            <div className="row-sub">该表情没有独立资源文件</div>
          ) : (
            assets.map((file) => (
              <div key={file.path} className="file-head" style={{ marginBottom: 4 }}>
                <span className="file-path">{file.path}</span>
                <Badge>{file.kind === 'code' ? '代码' : '资源'}</Badge>
                <span className="row-sub">{(file.size / 1024).toFixed(1)} KB</span>
              </div>
            ))
          )}
        </div>
      )}
    </Modal>
  )
}
