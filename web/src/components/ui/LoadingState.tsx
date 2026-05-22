import { Eyebrow } from './Eyebrow'

/* Editorial loading placeholder. Used in card bodies, panel content
   areas, and page-level slots while the pipeline waits for the backend
   to start streaming or between phases. */

type Size = 'sm' | 'md' | 'lg'

interface Props {
  label?: string
  size?: Size
  className?: string
}

const SIZE_CLASSES: Record<Size, { dot: string; gap: string; label: 'sm' | 'md' | 'lg' }> = {
  sm: { dot: 'w-1 h-1',     gap: 'gap-2', label: 'sm' },
  md: { dot: 'w-1.5 h-1.5', gap: 'gap-3', label: 'md' },
  lg: { dot: 'w-2 h-2',     gap: 'gap-4', label: 'lg' },
}

export function LoadingState({ label = 'Loading', size = 'md', className = '' }: Props) {
  const s = SIZE_CLASSES[size]
  return (
    <div
      className={`inline-flex items-center ${s.gap} ${className}`}
      role="status"
      aria-live="polite"
    >
      <span className="inline-flex items-center gap-1" aria-hidden>
        <span className={`${s.dot} bg-editorial-brass rounded-full animate-pulse`} style={{ animationDelay: '0ms' }} />
        <span className={`${s.dot} bg-editorial-brass rounded-full animate-pulse`} style={{ animationDelay: '180ms' }} />
        <span className={`${s.dot} bg-editorial-brass rounded-full animate-pulse`} style={{ animationDelay: '360ms' }} />
      </span>
      <Eyebrow size={s.label} tone="mute" as="span">{label}</Eyebrow>
    </div>
  )
}
