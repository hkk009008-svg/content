import { useState, type ReactNode } from 'react'
import { MICRO_LABEL } from '../ui'

/* Collapsible settings section. Encapsulates the toggle UI pattern
   repeated 10× in the original SettingsPanel monolith. */

interface Props {
  /** Plain text title (rendered as a standard micro-label heading). For richer headers
      with badges or color shifts, use `titleNode` instead. */
  title?: string
  /** Full title node — escape hatch for sections with badges, dual-color titles, etc. */
  titleNode?: ReactNode
  /** Default expanded state; can be controlled by passing both `expanded` + `onToggle`. */
  defaultExpanded?: boolean
  expanded?: boolean
  onToggle?: (next: boolean) => void
  rightSlot?: ReactNode
  children: ReactNode
}

export function SettingsSection({
  title,
  titleNode,
  defaultExpanded = false,
  expanded,
  onToggle,
  rightSlot,
  children,
}: Props) {
  const [local, setLocal] = useState(defaultExpanded)
  const isControlled = expanded !== undefined
  const isOpen = isControlled ? expanded! : local

  const toggle = () => {
    const next = !isOpen
    if (!isControlled) setLocal(next)
    onToggle?.(next)
  }

  return (
    <div>
      <button
        type="button"
        onClick={toggle}
        className="flex items-center justify-between w-full mt-5 mb-3 group"
        aria-expanded={isOpen}
      >
        {titleNode ?? (
          <h2 className={`${MICRO_LABEL} font-semibold flex items-center gap-2`}>
            {title}
          </h2>
        )}
        <span className="flex items-center gap-2">
          {rightSlot}
          <span className="text-mut text-xs">{isOpen ? '▾' : '▸'}</span>
        </span>
      </button>
      {isOpen && <div className="space-y-4">{children}</div>}
    </div>
  )
}
