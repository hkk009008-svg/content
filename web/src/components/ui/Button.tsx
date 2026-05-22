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
    'bg-editorial-brass text-editorial-ink ' +
    'hover:bg-editorial-brass-deep ' +
    'disabled:bg-editorial-rule disabled:text-editorial-ivory-faint',
  curtain:
    'bg-editorial-curtain text-editorial-ivory ' +
    'hover:bg-editorial-curtain-deep ' +
    'disabled:bg-editorial-rule disabled:text-editorial-ivory-faint',
  'curtain-outline':
    'border border-editorial-curtain text-editorial-curtain bg-transparent ' +
    'hover:bg-editorial-curtain hover:text-editorial-ivory ' +
    'disabled:border-editorial-rule disabled:text-editorial-ivory-faint disabled:hover:bg-transparent',
  'brass-outline':
    'border border-editorial-brass text-editorial-brass bg-transparent ' +
    'hover:bg-editorial-brass hover:text-editorial-ink ' +
    'disabled:border-editorial-rule disabled:text-editorial-ivory-faint disabled:hover:bg-transparent',
  'ivory-ghost':
    'border border-editorial-rule text-editorial-ivory ' +
    'hover:bg-editorial-ink-soft hover:border-editorial-rule-bright ' +
    'disabled:text-editorial-ivory-faint disabled:border-editorial-rule disabled:hover:bg-transparent',
  'rule-only':
    'text-editorial-ivory-mute hover:text-editorial-brass ' +
    'border-b border-transparent hover:border-editorial-brass ' +
    'disabled:text-editorial-ivory-faint disabled:hover:border-transparent',
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
  'focus-visible:ring-1 focus-visible:ring-editorial-brass focus-visible:ring-offset-2 ' +
  'focus-visible:ring-offset-editorial-ink'

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
