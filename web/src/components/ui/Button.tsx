import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

/* Editorial cinema button. Variant names map to the color token applied,
   so a JSX reader knows the visual outcome from the variant name alone.

   variant="brass"           → primary CTA (Submit, Save, Approve)
   variant="curtain"         → alert/destructive CTA (Delete, Abort, urgent)
   variant="curtain-outline" → cancel/abort variant (Strike, Stop) — outline that fills on hover
   variant="brass-outline"   → primary outline — quiet primary that fills on hover
   variant="ivory-ghost"     → secondary (Cancel, Back, dismiss)
   variant="rule-only"       → tertiary (subtle in-rail action) */

export type ButtonVariant =
  | 'brass'
  | 'curtain'
  | 'curtain-outline'
  | 'brass-outline'
  | 'ivory-ghost'
  | 'rule-only'

export type ButtonSize = 'sm' | 'md' | 'lg'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  isLoading?: boolean
  leftIcon?: ReactNode
  fullWidth?: boolean
}

const VARIANT: Record<ButtonVariant, string> = {
  brass:
    'bg-acc text-app ' +
    'hover:bg-acc ' +
    'disabled:bg-line disabled:text-dim',
  curtain:
    'bg-fail text-tx ' +
    'hover:bg-fail ' +
    'disabled:bg-line disabled:text-dim',
  'curtain-outline':
    'border border-fail text-fail bg-transparent ' +
    'hover:bg-fail hover:text-tx ' +
    'disabled:border-line disabled:text-dim disabled:hover:bg-transparent',
  'brass-outline':
    'border border-acc text-acc bg-transparent ' +
    'hover:bg-acc hover:text-app ' +
    'disabled:border-line disabled:text-dim disabled:hover:bg-transparent',
  'ivory-ghost':
    'border border-line text-tx ' +
    'hover:bg-panel hover:border-line ' +
    'disabled:text-dim disabled:border-line disabled:hover:bg-transparent',
  'rule-only':
    'text-mut hover:text-acc ' +
    'border-b border-transparent hover:border-acc ' +
    'disabled:text-dim disabled:hover:border-transparent',
}

const SIZE: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-eyebrow-lg',
  md: 'px-5 py-2.5 text-sm',
  lg: 'px-8 py-3.5 text-base',
}

const BASE =
  'font-mono tracking-wide-eyebrow uppercase ' +
  'transition-colors duration-150 ' +
  'disabled:cursor-not-allowed ' +
  'inline-flex items-center justify-center gap-2 ' +
  'active:translate-y-px focus-visible:outline-none ' +
  'focus-visible:ring-1 focus-visible:ring-acc focus-visible:ring-offset-2 ' +
  'focus-visible:ring-offset-app'

/** Build the className string for any element that should look like a Button.
   Use this when rendering as <a>, <Link>, or any non-button element where
   `<Button>` itself doesn't fit. Type-safe, no generics required. */
export function buttonClassName(opts: {
  variant?: ButtonVariant
  size?: ButtonSize
  fullWidth?: boolean
  className?: string
} = {}): string {
  const { variant = 'brass', size = 'md', fullWidth = false, className } = opts
  return [
    BASE,
    VARIANT[variant],
    SIZE[size],
    fullWidth ? 'w-full' : '',
    className ?? '',
  ].filter(Boolean).join(' ')
}

export const Button = forwardRef<HTMLButtonElement, Props>(function Button(
  {
    variant = 'brass',
    size = 'md',
    isLoading = false,
    leftIcon,
    fullWidth = false,
    className,
    disabled,
    children,
    type = 'button',
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || isLoading}
      aria-busy={isLoading || undefined}
      className={buttonClassName({ variant, size, fullWidth, className })}
      {...rest}
    >
      {isLoading ? <Spinner /> : leftIcon}
      {children}
    </button>
  )
})

function Spinner() {
  return (
    <span
      aria-hidden
      className="inline-block w-3 h-3 border border-current border-t-transparent rounded-full animate-spin"
    />
  )
}
