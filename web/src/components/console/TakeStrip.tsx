/**
 * TakeStrip — reusable 1-4 pane preview strip for take media.
 *
 * Renders side-by-side labeled panes for any combination of:
 *   - a keyframe still (img)
 *   - a driving-reference clip (video) — performance-capture input
 *   - a captured-performance clip (video) — performance-capture output
 *   - a motion render clip (video) — final cinema engine output
 *
 * Each pane is shown only when its URL prop is non-null/non-empty.
 * When no panes have content the component renders nothing.
 *
 * Pane order (pipeline order): keyframe → driving → performance → motion
 *
 * Used by:
 *   - ReviewStage (Performance Capture section: drivingUrl + performanceUrl)
 *   - Monitor (A3 — inline preview reel in Director's Console: all 4 panes)
 */

const API = '/api'

export interface TakeStripProps {
  keyframeUrl?: string | null
  /** Driving-reference video — input to the performance-capture stage */
  drivingUrl?: string | null
  /** Captured-performance video — output of the performance-capture stage */
  performanceUrl?: string | null
  /** Motion render video — final cinema engine output */
  motionUrl?: string | null
  apiBase?: string
  projectId?: string | null
  /** Override default labels. */
  labels?: {
    keyframe?: string
    driving?: string
    performance?: string
    motion?: string
  }
}

export default function TakeStrip({
  keyframeUrl,
  drivingUrl,
  performanceUrl,
  motionUrl,
  apiBase = '',
  projectId,
  labels,
}: TakeStripProps) {
  const base = apiBase || API
  const hasAny = Boolean(keyframeUrl || drivingUrl || performanceUrl || motionUrl)
  if (!hasAny) return null

  const resolve = (path: string) =>
    projectId
      ? `${base}/projects/${projectId}/file?path=${encodeURIComponent(path)}`
      : path

  const keyframeLabel = labels?.keyframe ?? 'Keyframe'
  const drivingLabel = labels?.driving ?? 'Driving reference'
  const performanceLabel = labels?.performance ?? 'Captured performance'
  const motionLabel = labels?.motion ?? 'Motion render'

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

      {drivingUrl ? (
        <div>
          <div className="text-eyebrow-lg uppercase text-editorial-ivory-mute mb-1">{drivingLabel}</div>
          <video
            src={resolve(drivingUrl)}
            controls
            muted
            loop
            className="w-full rounded border border-editorial-rule bg-black"
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
      ) : null}

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
      ) : null}
    </div>
  )
}
