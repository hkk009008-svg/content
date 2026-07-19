import type { ReactNode } from 'react'

/* Small inline status/label chip. Variant name maps directly to the token
   pair applied, so the visual result is legible from the variant alone. */

export type BadgeVariant = 'pri' | 'pod' | 'cloud' | 'ok' | 'warn' | 'fail' | 'neutral'

interface Props {
  variant: BadgeVariant
  children: ReactNode
  className?: string
}

const VARIANT: Record<BadgeVariant, string> = {
  pri: 'text-pri bg-pri-bg',
  pod: 'text-pod bg-pod-bg',
  cloud: 'text-mut bg-head',
  ok: 'text-ok bg-head',
  warn: 'text-warn bg-head',
  fail: 'text-fail bg-head',
  neutral: 'text-mut bg-head',
}

const BASE =
  'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wide font-medium'

export function Badge({ variant, children, className }: Props) {
  return (
    <span className={[BASE, VARIANT[variant], className ?? ''].filter(Boolean).join(' ')}>
      {variant === 'pod' && <span aria-hidden>⚙</span>}
      {children}
    </span>
  )
}
