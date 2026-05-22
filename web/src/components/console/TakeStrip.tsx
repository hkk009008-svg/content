/**
 * TakeStrip — reusable 1-3 pane preview strip for take media.
 *
 * Renders side-by-side labeled panes for any combination of:
 *   - a keyframe still (img)
 *   - a performance / driving-reference clip (video)
 *   - a motion / captured-performance clip (video)
 *
 * Each pane is shown only when its URL prop is non-null/non-empty.
 * When no panes have content the component renders nothing.
 *
 * Used by:
 *   - ReviewStage (Performance Capture section)
 *   - Monitor (A3 — inline preview reel in Director's Console)
 */

const API = '/api'

export interface TakeStripProps {
  keyframeUrl?: string | null
  performanceUrl?: string | null
  motionUrl?: string | null
  apiBase?: string
  projectId?: string | null
  /** Override default labels. Defaults: KEYFRAME / PERFORMANCE / MOTION */
  labels?: {
    keyframe?: string
    performance?: string
    motion?: string
  }
}

export default function TakeStrip({
  keyframeUrl,
  performanceUrl,
  motionUrl,
  apiBase = '',
  projectId,
  labels,
}: TakeStripProps) {
  const base = apiBase || API
  const hasAny = Boolean(keyframeUrl || performanceUrl || motionUrl)
  if (!hasAny) return null

  const resolve = (path: string) =>
    projectId
      ? `${base}/projects/${projectId}/file?path=${encodeURIComponent(path)}`
      : path

  const keyframeLabel = labels?.keyframe ?? 'Keyframe'
  const performanceLabel = labels?.performance ?? 'Driving reference'
  const motionLabel = labels?.motion ?? 'Captured performance'

  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {keyframeUrl ? (
        <div>
          <div className="text-eyebrow-lg uppercase text-editorial-ivory-mute mb-1">{keyframeLabel}</div>
          <img
            src={resolve(keyframeUrl)}
            className="w-full rounded border border-editorial-rule object-cover"
          />
        </div>
      ) : null}

      {performanceUrl ? (
        <div>
          <div className="text-eyebrow-lg uppercase text-editorial-ivory-mute mb-1">{performanceLabel}</div>
          <video
            src={resolve(performanceUrl)}
            controls
            muted
            loop
            className="w-full rounded border border-editorial-rule bg-black"
          />
        </div>
      ) : (
        <div className="text-xs text-editorial-ivory-mute">No driving reference (auto-synth path).</div>
      )}

      {motionUrl ? (
        <div>
          <div className="text-eyebrow-lg uppercase text-editorial-ivory-mute mb-1">{motionLabel}</div>
          <video
            src={resolve(motionUrl)}
            controls
            muted
            loop
            className="w-full rounded border border-editorial-rule bg-black"
          />
        </div>
      ) : (
        <div className="text-xs text-editorial-ivory-mute self-center">Performance not yet captured.</div>
      )}
    </div>
  )
}
