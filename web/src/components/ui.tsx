import type { ReactNode } from 'react'

export function Spinner({ label = '加载中…' }: { label?: string }) {
  return (
    <div className="loading">
      <span className="spinner" />
      <span>{label}</span>
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Alert({
  kind = 'info',
  children,
}: {
  kind?: 'info' | 'error' | 'success' | 'warn'
  children: ReactNode
}) {
  const icon = { info: 'ℹ', error: '✕', success: '✓', warn: '!' }[kind]
  return (
    <div className={`alert alert-${kind}`}>
      <span aria-hidden>{icon}</span>
      <div>{children}</div>
    </div>
  )
}

export function Badge({
  children,
  tone,
}: {
  children: ReactNode
  tone?: 'on' | 'off' | 'info' | 'warn'
}) {
  return <span className={`badge${tone ? ` ${tone}` : ''}`}>{children}</span>
}

export function Modal({
  title,
  onClose,
  children,
  footer,
}: {
  title: ReactNode
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
}) {
  return (
    <div
      className="modal-mask"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="modal" role="dialog" aria-modal="true">
        <div className="modal-head">
          <div className="modal-title">{title}</div>
          <button className="modal-close" onClick={onClose} aria-label="关闭">
            ×
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

/** 把后端返回的来源标识转成易读文案。 */
export function sourceLabel(source: string): string {
  if (source === 'builtin') return '内置'
  if (source.startsWith('repo:')) return source.slice(5)
  return source
}
