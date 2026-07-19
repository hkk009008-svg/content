import type { ReactNode } from 'react'
import { MICRO_LABEL, Toggle, type SelectOption } from '../../ui'

/* Token-styled control rows shared across the SettingsInspector sections.
   Centralized here so the five sections stay declarative and no editorial-*
   class leaks in. Tokens only: bg-panel / border-line / text-tx|mut|acc. */

const FIELD_CLS =
  'w-full rounded border border-line bg-panel px-2 py-1.5 text-[11px] text-tx ' +
  'focus:border-acc focus:outline-none'

function Hint({ children }: { children?: ReactNode }) {
  return children ? (
    <p className="mt-1 text-[10px] leading-tight text-mut">{children}</p>
  ) : null
}

interface RangeRowProps {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  format?: (v: number) => string
  hint?: ReactNode
}

export function RangeRow({ label, value, min, max, step, onChange, format, hint }: RangeRowProps) {
  const isInt = step >= 1
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className={MICRO_LABEL}>{label}</span>
        <span className="font-mono text-[11px] font-semibold text-acc">
          {format ? format(value) : value}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(isInt ? parseInt(e.target.value, 10) : parseFloat(e.target.value))}
        aria-label={label}
        className="h-1 w-full accent-acc"
      />
      <Hint>{hint}</Hint>
    </div>
  )
}

interface ToggleRowProps {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
  hint?: ReactNode
  disabled?: boolean
  right?: ReactNode
}

export function ToggleRow({ label, checked, onChange, hint, disabled, right }: ToggleRowProps) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 text-[11px] text-tx">
          <span>{label}</span>
          {right}
        </div>
        <Hint>{hint}</Hint>
      </div>
      <Toggle checked={checked} onChange={onChange} disabled={disabled} aria-label={label} />
    </div>
  )
}

interface SelectRowProps {
  label: string
  value: string
  options: SelectOption[] | string[]
  onChange: (v: string) => void
  hint?: ReactNode
}

function normalize(options: SelectOption[] | string[]): SelectOption[] {
  return options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o))
}

export function SelectRow({ label, value, options, onChange, hint }: SelectRowProps) {
  return (
    <div>
      <label className={`${MICRO_LABEL} mb-1 block`}>{label}</label>
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={FIELD_CLS}
      >
        {normalize(options).map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <Hint>{hint}</Hint>
    </div>
  )
}

interface NumberRowProps {
  label: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
  placeholder?: string
  hint?: ReactNode
}

export function NumberRow({ label, value, onChange, min, max, step, placeholder, hint }: NumberRowProps) {
  return (
    <div>
      <label className={`${MICRO_LABEL} mb-1 block`}>{label}</label>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
        aria-label={label}
        className={`${FIELD_CLS} font-mono`}
      />
      <Hint>{hint}</Hint>
    </div>
  )
}

interface TextRowProps {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  hint?: ReactNode
}

export function TextRow({ label, value, onChange, placeholder, hint }: TextRowProps) {
  return (
    <div>
      <label className={`${MICRO_LABEL} mb-1 block`}>{label}</label>
      <input
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
        className={FIELD_CLS}
      />
      <Hint>{hint}</Hint>
    </div>
  )
}
