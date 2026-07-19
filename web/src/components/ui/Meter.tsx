import type { ReactNode } from 'react'

/* Labeled progress bar. Tone name maps directly to the fill token. */

export type MeterTone = 'acc' | 'pri' | 'pod' | 'ok' | 'warn' | 'fail'

interface Props {
  value: number
  max?: number
  tone?: MeterTone
  label?: string
  right?: ReactNode
}

const TONE: Record<MeterTone, string> = {
  acc: 'bg-acc',
  pri: 'bg-pri',
  pod: 'bg-pod',
  ok: 'bg-ok',
  warn: 'bg-warn',
  fail: 'bg-fail',
}

export function Meter({ value, max = 1, tone = 'acc', label, right }: Props) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div>
      {(label || right) && (
        <div className="mb-1 flex items-center justify-between text-[10px] text-mut">
          {label && <span>{label}</span>}
          {right && <span>{right}</span>}
        </div>
      )}
      <div className="h-1 w-full overflow-hidden rounded-full bg-head">
        <div className={['h-full rounded-full', TONE[tone]].join(' ')} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
