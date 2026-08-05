/* Compact pill-styled native <select>. Accepts either full {value,label}
   options or a plain string[] shorthand (value === label). */

export interface SelectOption {
  value: string
  label: string
  /** Renders as a disabled <option> (e.g. a server-marked non-selectable
   *  engine surfaced so its current-value/history context stays visible). */
  disabled?: boolean
  /** Native <option title> tooltip — pair with `disabled` to explain why. */
  title?: string
}

interface Props {
  value: string
  onChange: (value: string) => void
  options: SelectOption[] | string[]
  'aria-label': string
  'aria-describedby'?: string
}

function normalize(options: SelectOption[] | string[]): SelectOption[] {
  return options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o))
}

export function SelectPill({
  value,
  onChange,
  options,
  'aria-label': ariaLabel,
  'aria-describedby': ariaDescribedBy,
}: Props) {
  return (
    <select
      aria-label={ariaLabel}
      aria-describedby={ariaDescribedBy}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-full border border-line bg-panel px-2 py-0.5 text-[11px] text-tx focus:border-acc focus:outline-none"
    >
      {normalize(options).map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled} title={o.title}>
          {o.label}
        </option>
      ))}
    </select>
  )
}
