import { createElement, type ReactNode } from 'react'

/* The mono uppercase tracked label that runs throughout the editorial
   system. Codifies the 58 ad-hoc `font-mono text-eyebrow tracking-wide-eyebrow
   uppercase ...` sites the audit found, and adds `as` for the cases where
   the label is structurally a heading. */

type Size = 'sm' | 'md' | 'lg'
type Tone = 'mute' | 'soft' | 'ivory' | 'brass' | 'curtain'
type As   = 'span' | 'div' | 'p' | 'label' | 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6'

interface Props {
  size?: Size
  tone?: Tone
  as?: As
  className?: string
  children: ReactNode
}

const SIZE: Record<Size, string> = {
  sm: 'text-eyebrow-sm',
  md: 'text-eyebrow',
  lg: 'text-eyebrow-lg',
}

const TONE: Record<Tone, string> = {
  mute:    'text-editorial-ivory-mute',
  soft:    'text-editorial-ivory-soft',
  ivory:   'text-editorial-ivory',
  brass:   'text-editorial-brass',
  curtain: 'text-editorial-curtain',
}

export function Eyebrow({
  size = 'md',
  tone = 'mute',
  as = 'div',
  className,
  children,
}: Props) {
  return createElement(
    as,
    {
      className: `font-mono ${SIZE[size]} ${TONE[tone]} tracking-wide-eyebrow uppercase ${className ?? ''}`.trim(),
    },
    children,
  )
}
