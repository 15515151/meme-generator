import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError, api, type MemeSummary } from '../api'
import { useToast } from '../components/Toast'
import { Alert, Badge, Card, Empty, Modal, Spinner, formatSize, sourceLabel } from '../components/ui'
import { IconBan, IconCheck, IconEye, IconMeme, IconRefresh, IconSearch } from '../components/icons'

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
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())

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

  // 输入防抖，避免每敲一个字都请求
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
      setItems((prev) => prev.map((item) => (item.key === meme.key ? { ...item, disabled } : item)))
      if (status !== 'all') void load()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '操作失败')
    } finally {
      setBusyKey('')
    }
  }

  async function batch(keys: string[], disabled: boolean) {
    if (keys.length === 0) return
    const verb = disabled ? '封禁' : '启用'
    if (!window.confirm(`确定${verb}选中的 ${keys.length} 个表情吗？`)) return
    try {
      const result = await api.batchToggle(keys, disabled)
      toast.success(`已${verb} ${result.updated.length} 个表情`)
      setSelectedKeys(new Set())
      void load()
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : '批量操作失败')
    }
  }

  function toggleSelect(key: string) {
    setSelectedKeys((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const allSelected = items.length > 0 && items.every((item) => selectedKeys.has(item.key))

  return (
    <>
      {error && <Alert kind="error">{error}</Alert>}

      <div className="toolbar">
        <div className="search">
          <span className="search-icon">
            <IconSearch size={15} />
          </span>
          <input
            className="input"
            placeholder="搜索 key、关键词或标签…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)}>
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
        <button className="btn btn-icon" onClick={() => void load()} title="刷新">
          <IconRefresh size={15} />
        </button>
      </div>

      <Card
        title="表情"
        count={`共 ${counts.total} 个 · 启用 ${counts.enabled} · 封禁 ${counts.disabled}`}
        actions={
          selectedKeys.size > 0 ? (
            <>
              <span className="text-sm text-muted">已选 {selectedKeys.size} 个</span>
              <button className="btn btn-sm" onClick={() => void batch([...selectedKeys], false)}>
                <IconCheck size={14} />
                启用
              </button>
              <button className="btn btn-sm btn-danger" onClick={() => void batch([...selectedKeys], true)}>
                <IconBan size={14} />
                封禁
              </button>
              <button className="btn btn-sm btn-ghost" onClick={() => setSelectedKeys(new Set())}>
                取消
              </button>
            </>
          ) : (
            <>
              <button className="btn btn-sm" onClick={() => void batch(items.map((i) => i.key), false)} disabled={!items.length}>
                <IconCheck size={14} />
                全部启用
              </button>
              <button className="btn btn-sm" onClick={() => void batch(items.map((i) => i.key), true)} disabled={!items.length}>
                <IconBan size={14} />
                全部封禁
              </button>
            </>
          )
        }
        pad
      >
        {loading && items.length === 0 ? (
          <div className="meme-grid">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="meme-card">
                <div className="skeleton" style={{ aspectRatio: '4 / 3' }} />
                <div className="meme-body">
                  <div className="skeleton" style={{ height: 14, width: '60%' }} />
                  <div className="skeleton" style={{ height: 12, width: '40%' }} />
                </div>
              </div>
            ))}
          </div>
        ) : items.length === 0 ? (
          <Empty
            icon={<IconMeme size={26} />}
            title={query || status !== 'all' || source ? '没有匹配的表情' : '还没有加载任何表情'}
            desc={query || status !== 'all' || source ? '换个关键词或调整筛选条件试试' : undefined}
          />
        ) : (
          <>
            <div className="row mb-4" style={{ gap: 16 }}>
              <label className="switch" style={{ fontSize: 12.5 }}>
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(e) => {
                    if (e.target.checked) setSelectedKeys(new Set(items.map((i) => i.key)))
                    else setSelectedKeys(new Set())
                  }}
                />
                <span className="switch-track" />
                <span>全选当前结果</span>
              </label>
            </div>

            <div className="meme-grid">
              {items.map((meme) => (
                <MemeCard
                  key={meme.key}
                  meme={meme}
                  busy={busyKey === meme.key}
                  selected={selectedKeys.has(meme.key)}
                  onSelect={() => toggleSelect(meme.key)}
                  onToggle={(disabled) => void toggle(meme, disabled)}
                  onOpen={() => setSelected(meme)}
                />
              ))}
            </div>
          </>
        )}
      </Card>

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
  selected,
  onSelect,
  onToggle,
  onOpen,
}: {
  meme: MemeSummary
  busy: boolean
  selected: boolean
  onSelect: () => void
  onToggle: (disabled: boolean) => void
  onOpen: () => void
}) {
  const [src, setSrc] = useState('')
  const [failed, setFailed] = useState(false)
  const [visible, setVisible] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const cardRef = useRef<HTMLDivElement>(null)
  const objectUrl = useRef('')

  // 预览要真的渲染图片，代价不低；滚动到视野内再生成
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
      { rootMargin: '220px' },
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
    <div
      ref={cardRef}
      className={`meme-card${meme.disabled ? ' disabled' : ''}`}
      style={selected ? { borderColor: 'var(--accent)', boxShadow: '0 0 0 3px var(--accent-soft)' } : undefined}
    >
      <div className="meme-thumb">
        {src && !failed ? (
          <img src={src} alt={meme.key} loading="lazy" />
        ) : failed ? (
          <div className="placeholder">预览生成失败</div>
        ) : (
          <Spinner />
        )}
        <button
          className="thumb-action"
          onClick={() => setReloadKey((k) => k + 1)}
          title="重新生成预览"
        >
          刷新
        </button>
      </div>

      <div className="meme-body">
        {/* 尺寸通过 CSS 变量传入，旋钮位置会跟着算，不再出现溢出 */}
        <label className="switch" style={{ '--switch-w': '32px', '--switch-h': '18px' } as React.CSSProperties}>
          <input type="checkbox" checked={selected} onChange={onSelect} />
          <span className="switch-track" />
          <span className="meme-key">{meme.key}</span>
        </label>

        <div className="meme-tags">
          <Badge tone={meme.disabled ? 'off' : 'on'} dot>
            {meme.disabled ? '已封禁' : '启用中'}
          </Badge>
          {meme.source !== 'builtin' && <Badge tone="info">{sourceLabel(meme.source)}</Badge>}
          <Badge>
            {meme.min_images > 0 ? `${meme.min_images} 图` : ''}
            {meme.min_images > 0 && meme.min_texts > 0 ? ' + ' : ''}
            {meme.min_texts > 0 ? `${meme.min_texts} 文` : ''}
            {meme.min_images === 0 && meme.min_texts === 0 ? '无参数' : ''}
          </Badge>
        </div>

        {meme.keywords.length > 0 && (
          <div className="meme-meta" title={meme.keywords.join('、')}>
            {meme.keywords.join('、')}
          </div>
        )}

        <div className="meme-actions">
          <button className="btn btn-sm" onClick={onOpen}>
            <IconEye size={13} />
            预览
          </button>
          <button
            className={`btn btn-sm ${meme.disabled ? 'btn-success' : 'btn-danger'}`}
            disabled={busy}
            onClick={() => onToggle(!meme.disabled)}
          >
            {busy ? <span className="spinner" /> : meme.disabled ? <IconCheck size={13} /> : <IconBan size={13} />}
            {meme.disabled ? '启用' : '封禁'}
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
            {meme.disabled ? <IconCheck size={14} /> : <IconBan size={14} />}
            {meme.disabled ? '启用此表情' : '封禁此表情'}
          </button>
        </>
      }
    >
      <div className="row mb-4">
        <Badge tone={meme.disabled ? 'off' : 'on'} dot>
          {meme.disabled ? '已封禁' : '启用中'}
        </Badge>
        <Badge tone="info">来源：{sourceLabel(meme.source)}</Badge>
        <Badge>{paramText}</Badge>
      </div>

      {error && <Alert kind="error">{error}</Alert>}

      <div className="preview-box">
        {loading ? <Spinner label="生成预览中…" /> : src ? <img src={src} alt={meme.key} /> : null}
        {!loading && !src && !error && <div className="text-dim text-sm">暂无预览</div>}
      </div>

      {meme.min_images > 0 && (
        <Alert kind="info">
          预览使用随机图片生成；实际调用时请自行上传图片。参数：{paramText}
        </Alert>
      )}

      {meme.min_texts > 0 && (
        <>
          <div className="field">
            <label htmlFor="preview-texts">
              预览文本（逗号分隔，最多 {meme.max_texts || meme.min_texts} 段）
            </label>
            <input
              id="preview-texts"
              className="input"
              value={texts}
              onChange={(e) => setTexts(e.target.value)}
              placeholder={meme.default_texts.join(',')}
            />
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => void generate()} disabled={loading}>
            {loading ? <span className="spinner" /> : <IconRefresh size={14} />}
            重新生成
          </button>
        </>
      )}

      {meme.keywords.length > 0 && (
        <div className="text-sm text-muted mt-3">关键词：{meme.keywords.join('、')}</div>
      )}

      <div className="text-sm text-dim mt-2">
        创建于 {new Date(meme.date_created).toLocaleDateString()} · 修改于{' '}
        {new Date(meme.date_modified).toLocaleDateString()}
      </div>

      {assets && (
        <div className="mt-4">
          <div className="card-title mb-3">资源文件（{assets.length}）</div>
          {assets.length === 0 ? (
            <div className="text-sm text-dim">该表情没有独立资源文件</div>
          ) : (
            assets.map((file) => (
              <div key={file.path} className="file-row">
                <span className="file-path" title={file.path}>
                  {file.path}
                </span>
                <Badge>{file.kind === 'code' ? '代码' : '资源'}</Badge>
                <span className="file-size">{formatSize(file.size)}</span>
              </div>
            ))
          )}
        </div>
      )}
    </Modal>
  )
}
