import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'

import { Check, ChevronDown } from 'lucide-react'

export interface SelectOption {
  value: string
  label: ReactNode
  /** 下拉里显示的完整名称，缺省时用 label（用于 label 被截断的场景） */
  title?: string
}

/**
 * 玻璃风格的下拉选择器。
 *
 * 原生 <select> 的展开列表由操作系统绘制，无法跟随玻璃质感，所以这里自己实现：
 * 触发按钮与列表都在 body 上以 portal 渲染，避免被卡片的 overflow 裁掉。
 */
export function Select({
  value,
  options,
  onChange,
  placeholder = '请选择',
  disabled,
  ariaLabel,
  className,
}: {
  value: string
  options: SelectOption[]
  onChange: (value: string) => void
  placeholder?: string
  disabled?: boolean
  ariaLabel?: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({})
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const listId = useId()

  const selected = useMemo(
    () => options.find((option) => option.value === value),
    [options, value],
  )

  /** 菜单宽度跟随触发器，并在视口内定位（下方空间不足时向上展开）。 */
  const positionMenu = useCallback(() => {
    const trigger = triggerRef.current
    if (!trigger) return
    const rect = trigger.getBoundingClientRect()
    const gap = 6
    const maxHeight = 300
    const spaceBelow = window.innerHeight - rect.bottom - gap
    const openUpward = spaceBelow < Math.min(maxHeight, 180) && rect.top > spaceBelow

    setMenuStyle({
      position: 'fixed',
      left: rect.left,
      width: rect.width,
      maxHeight: Math.min(maxHeight, openUpward ? rect.top - gap - 8 : spaceBelow - 8),
      ...(openUpward
        ? { bottom: window.innerHeight - rect.top + gap }
        : { top: rect.bottom + gap }),
    })
  }, [])

  useLayoutEffect(() => {
    if (!open) return
    positionMenu()
    const index = options.findIndex((option) => option.value === value)
    setActiveIndex(index >= 0 ? index : 0)
  }, [open, options, value, positionMenu])

  useEffect(() => {
    if (!open) return

    function onPointerDown(event: MouseEvent) {
      const target = event.target as Node
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) return
      setOpen(false)
    }

    function onScrollOrResize() {
      positionMenu()
    }

    document.addEventListener('mousedown', onPointerDown)
    // 捕获阶段监听滚动，页面内任意滚动容器都能触发重新定位
    window.addEventListener('scroll', onScrollOrResize, true)
    window.addEventListener('resize', onScrollOrResize)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      window.removeEventListener('scroll', onScrollOrResize, true)
      window.removeEventListener('resize', onScrollOrResize)
    }
  }, [open, positionMenu])

  function commit(index: number) {
    const option = options[index]
    if (!option) return
    onChange(option.value)
    setOpen(false)
    triggerRef.current?.focus()
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (disabled) return
    if (!open) {
      if (['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(event.key)) {
        event.preventDefault()
        setOpen(true)
      }
      return
    }
    switch (event.key) {
      case 'Escape':
        event.preventDefault()
        setOpen(false)
        break
      case 'ArrowDown':
        event.preventDefault()
        setActiveIndex((i) => Math.min(i + 1, options.length - 1))
        break
      case 'ArrowUp':
        event.preventDefault()
        setActiveIndex((i) => Math.max(i - 1, 0))
        break
      case 'Home':
        event.preventDefault()
        setActiveIndex(0)
        break
      case 'End':
        event.preventDefault()
        setActiveIndex(options.length - 1)
        break
      case 'Enter':
      case ' ':
        event.preventDefault()
        commit(activeIndex)
        break
    }
  }

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={`select${open ? ' open' : ''}${className ? ` ${className}` : ''}`}
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        onKeyDown={onKeyDown}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-haspopup="listbox"
        aria-label={ariaLabel}
      >
        <span className={`select-value${selected ? '' : ' placeholder'}`}>
          {selected ? selected.label : placeholder}
        </span>
        <ChevronDown size={15} className="select-caret" />
      </button>

      {open &&
        createPortal(
          <div
            ref={menuRef}
            id={listId}
            className="select-menu glass"
            style={menuStyle}
            role="listbox"
            aria-label={ariaLabel}
          >
            {options.length === 0 ? (
              <div className="select-empty">没有可选项</div>
            ) : (
              options.map((option, index) => (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={option.value === value}
                  title={option.title}
                  className={`select-option${option.value === value ? ' selected' : ''}${
                    index === activeIndex ? ' active' : ''
                  }`}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => commit(index)}
                >
                  <span className="select-option-label">{option.label}</span>
                  {option.value === value && <Check size={14} />}
                </button>
              ))
            )}
          </div>,
          document.body,
        )}
    </>
  )
}
