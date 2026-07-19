import { useState, type ReactNode } from 'react'

/* Collapsible panel section. The disclosure button holds only the chevron
   + title (so its accessible name is just the title); `right` renders as a
   sibling so it can safely hold interactive content of its own. */

interface Props {
  title: string
  children: ReactNode
  defaultOpen?: boolean
  right?: ReactNode
}

export function Section({ title, children, defaultOpen = true, right }: Props) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-b border-line">
      <div className="flex items-center justify-between px-3 py-2">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-mut"
        >
          <span aria-hidden className={['transition-transform', open ? 'rotate-90' : ''].join(' ')}>
            ›
          </span>
          {title}
        </button>
        {right}
      </div>
      {open && <div className="px-3 pb-3">{children}</div>}
    </div>
  )
}
