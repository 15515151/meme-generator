import type { ReactNode } from 'react'

import { IconInfo, IconX, IconCheck } from './icons'

export function Spinner({ label }: { label?: string }) {
  if (!label) return <span className="spinner" />
  return (
    <div className="loading">
      <span className="spinner" />
      <span>{label}</span>
    </div>
  )
}

export function Empty({
  icon,
  title,
  desc,
  action,
}: {
  icon?: ReactNode
  title: string
  desc?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="empty">
      {icon && <div className="empty-icon">{icon}</div>}
      <div className="empty-title">{title}</div>
      {desc && <div className="empty-desc">{desc}</div>}
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  )
}

export function Alert({
  kind = 'info',
  children,
}: {
  kind?: 'info' | 'error' | 'success' | 'warn'
  children: ReactNode
}) {
  const icon =
    kind === 'success' ? <IconCheck size={15} /> : kind === 'error' ? <IconX size={15} /> : <IconInfo size={15} />
  return (
    <div className={`alert alert-${kind}`}>
      <span className="alert-icon">{icon}</span>
      <div style={{ minWidth: 0 }}>{children}</div>
    </div>
  )
}

export function Badge({
  children,
  tone,
  dot,
}: {
  children: ReactNode
  tone?: 'on' | 'off' | 'info' | 'warn'
  dot?: boolean
}) {
  return (
    <span className={`badge${tone ? ` ${tone}` : ''}${dot ? ' badge-dot' : ''}`}>
      {children}
    </span>
  )
}

export function Card({
  title,
  count,
  actions,
  children,
  pad,
}: {
  title?: ReactNode
  count?: ReactNode
  actions?: ReactNode
  children: ReactNode
  pad?: boolean
}) {
  if (!title && !actions) {
    return <div className={`card${pad ? ' card-pad' : ''}`}>{children}</div>
  }
  return (
    <div className="card">
      <div className="card-head">
        <h2 className="card-title">
          {title}
          {count !== undefined && count !== null && <span className="count"> {count}</span>}
        </h2>
        {actions && <div className="card-actions">{actions}</div>}
      </div>
      {pad ? <div className="card-body">{children}</div> : children}
    </div>
  )
}

export function StatCard({
  label,
  value,
  icon,
  tone,
  hint,
  small,
}: {
  label: string
  value: ReactNode
  icon?: ReactNode
  tone?: 'ok' | 'warn' | 'danger'
  hint?: ReactNode
  small?: boolean
}) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <span className="stat-label">{label}</span>
        {icon && <span className={`stat-icon${tone ? ` ${tone}` : ''}`}>{icon}</span>}
      </div>
      <div className={`stat-value${small ? ' small' : ''}`}>{value}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  )
}

export function Modal({
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  title: ReactNode
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  return (
    <div
      className="modal-mask"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        style={wide ? { maxWidth: 860 } : undefined}
      >
        <div className="modal-head">
          <div className="modal-title">{title}</div>
          <button className="modal-close" onClick={onClose} aria-label="关闭">
            <IconX size={18} />
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  )
}

export function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label?: string
  disabled?: boolean
}) {
  return (
    <label className="switch">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="switch-track" />
      {label && <span>{label}</span>}
    </label>
  )
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T
  onChange: (next: T) => void
  options: { value: T; label: ReactNode }[]
}) {
  return (
    <div className="segmented">
      {options.map((option) => (
        <button
          key={option.value}
          className={value === option.value ? 'active' : ''}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

/** 把后端返回的来源标识转成易读文案。 */
export function sourceLabel(source: string): string {
  if (source === 'builtin') return '内置'
  if (source.startsWith('repo:')) return source.slice(5)
  return source
}

/** 相对时间，列表里比绝对时间更易读。 */
export function relativeTime(seconds: number | null | undefined): string {
  if (!seconds) return '—'
  const diff = Date.now() / 1000 - seconds
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 2592000) return `${Math.floor(diff / 86400)} 天前`
  return new Date(seconds * 1000).toLocaleDateString()
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
