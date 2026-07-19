/* 30x16 pill switch. On-state uses the accent token pair; off-state is a
   plain outlined pill. Root is a native <button role="switch"> so screen
   readers get toggle semantics for free. */

interface Props {
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  'aria-label': string
}

export function Toggle({ checked, onChange, disabled, 'aria-label': ariaLabel }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={[
        'relative inline-flex h-4 w-[30px] shrink-0 items-center rounded-full border transition-colors',
        'disabled:opacity-40 disabled:cursor-not-allowed',
        checked ? 'bg-acc-dim border-acc' : 'bg-panel border-line',
      ].join(' ')}
    >
      <span
        aria-hidden
        className={[
          'inline-block h-3 w-3 rounded-full bg-tx transition-transform',
          checked ? 'translate-x-[15px]' : 'translate-x-0.5',
        ].join(' ')}
      />
    </button>
  )
}
