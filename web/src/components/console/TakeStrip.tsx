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

/** Cascade decision metadata — mirrors TakeRecord.cascade_metadata (Session 6 P2-3). */
interface CascadeMetadata {
  engine: string
  score?: number
  threshold?: number
  fallback?: boolean
  attempts?: string[]
}

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
  /** Optional cascade metadata — renders "via {engine}" chip + FALLBACK badge
   *  below the motion pane using console-* palette only. */
  cascadeMetadata?: CascadeMetadata | null
  /** Lip-sync overlay cascade (NF-4, P1-3): dialogue takes carry a SECOND
   *  cascade record at take.metadata.lipsync_cascade — cascade_metadata on
   *  those takes holds the VIDEO cascade. Renders "lipsync via {engine}". */
  lipsyncCascadeMetadata?: CascadeMetadata | null
}

/** Engine/score/fallback chip row — shared by the video and lipsync rows. */
function CascadeChips({ meta, label }: { meta?: CascadeMetadata | null; label?: string }) {
  if (!meta) return null
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      <span className="rounded bg-console-surface-2 px-1.5 py-0.5 text-eyebrow text-console-ink-dim">
        {label ? `${label} via ${meta.engine}` : `via ${meta.engine}`}
      </span>
      {meta.score != null && meta.threshold != null && (
        <span className={`font-mono text-eyebrow ${
          meta.score >= meta.threshold
            ? 'text-console-gold'
            : 'text-console-ink-dim'
        }`}>
          {meta.score.toFixed(3)}
        </span>
      )}
      {meta.fallback && (
        <span className="rounded bg-console-accent/20 px-1.5 py-0.5 text-eyebrow text-console-accent">
          ⚠ FALLBACK
        </span>
      )}
    </div>
  )
}

export default function TakeStrip({
  keyframeUrl,
  drivingUrl,
  performanceUrl,
  motionUrl,
  apiBase = '',
  projectId,
  labels,
  cascadeMetadata,
  lipsyncCascadeMetadata,
}: TakeStripProps) {
  const base = apiBase || '/api'
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
          <div className="text-eyebrow-lg uppercase text-console-ink-dim mb-1">{keyframeLabel}</div>
          <img
            src={resolve(keyframeUrl)}
            className="w-full rounded border border-console-rule object-cover"
          />
        </div>
      ) : null}

      {drivingUrl ? (
        <div>
          <div className="text-eyebrow-lg uppercase text-console-ink-dim mb-1">{drivingLabel}</div>
          <video
            src={resolve(drivingUrl)}
            controls
            muted
            loop
            className="w-full rounded border border-console-rule bg-black"
          />
        </div>
      ) : null}

      {performanceUrl ? (
        <div>
          <div className="text-eyebrow-lg uppercase text-console-ink-dim mb-1">{performanceLabel}</div>
          <video
            src={resolve(performanceUrl)}
            controls
            muted
            loop
            className="w-full rounded border border-console-rule bg-black"
          />
        </div>
      ) : null}

      {motionUrl ? (
        <div>
          <div className="text-eyebrow-lg uppercase text-console-ink-dim mb-1">{motionLabel}</div>
          <video
            src={resolve(motionUrl)}
            controls
            muted
            loop
            className="w-full rounded border border-console-rule bg-black"
          />
          <CascadeChips meta={cascadeMetadata} />
          <CascadeChips meta={lipsyncCascadeMetadata} label="lipsync" />
        </div>
      ) : null}
    </div>
  )
}
