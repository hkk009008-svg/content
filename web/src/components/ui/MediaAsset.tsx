import { useMediaAsset } from '../../lib/useMediaAsset'
import { LoadingState } from './LoadingState'
import { MICRO_LABEL } from './index'

/**
 * MediaAsset — renders a project image/video URL through its explicit
 * fetch state (slice 10, Product invariant #6: portable persistence) instead
 * of handing a raw `src` straight to `<img>`/`<video>` and letting a 403/404
 * render as a silent blank box. See `useMediaAsset` for the state machine.
 *
 * `className` sizes/frames the whole slot (aspect ratio, rounding, border) --
 * it applies uniformly whether the slot ends up showing the loaded media or
 * a placeholder, so a shot's layout doesn't jump between states.
 */
export interface MediaAssetProps {
  kind: 'image' | 'video'
  url: string | null | undefined
  alt?: string
  className?: string
  /** Shown for the 'idle' state (no url at all -- nothing generated yet). */
  emptyLabel?: string
  objectFit?: 'cover' | 'contain'
  controls?: boolean
  muted?: boolean
  loop?: boolean
}

export default function MediaAsset({
  kind,
  url,
  alt = '',
  className = '',
  emptyLabel = 'No media yet',
  objectFit = 'cover',
  controls = false,
  muted = false,
  loop = false,
}: MediaAssetProps) {
  const { state, src } = useMediaAsset(url)
  const frameClass = `relative overflow-hidden ${className}`.trim()

  if (state === 'idle') {
    return (
      <div className={frameClass} data-media-state="idle">
        <div className="flex h-full w-full items-center justify-center bg-head">
          <span className={MICRO_LABEL}>{emptyLabel}</span>
        </div>
      </div>
    )
  }

  if (state === 'loading') {
    return (
      <div className={frameClass} data-media-state="loading">
        <div className="flex h-full w-full items-center justify-center bg-head">
          <LoadingState label="Loading" size="sm" />
        </div>
      </div>
    )
  }

  if (state === 'missing') {
    return (
      <div className={frameClass} data-media-state="missing">
        <div className="flex h-full w-full flex-col items-center justify-center gap-1 bg-head">
          <span className={MICRO_LABEL.replace('text-mut', 'text-fail')}>Media missing</span>
          <span className="text-eyebrow text-mut">The file for this take could not be found.</span>
        </div>
      </div>
    )
  }

  // 'ready' | 'migrated'
  const fit = objectFit === 'contain' ? 'object-contain' : 'object-cover'
  return (
    <div className={frameClass} data-media-state={state}>
      {kind === 'image' ? (
        // eslint-disable-next-line jsx-a11y/alt-text -- alt is always forwarded via props
        <img src={src ?? undefined} alt={alt} className={`h-full w-full ${fit}`} />
      ) : (
        <video
          src={src ?? undefined}
          controls={controls}
          muted={muted}
          loop={loop}
          className={`h-full w-full ${fit}`}
        />
      )}
      {state === 'migrated' && (
        <div
          className="absolute inset-x-0 bottom-0 bg-black/70 px-1.5 py-0.5 text-eyebrow text-tx"
          data-media-migrated-note
        >
          Project relocated — showing media from its new location
        </div>
      )}
    </div>
  )
}
