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

import { fileUrl } from '../../lib/mediaUrl'
import type { CascadeMetadata, LipsyncValidationState } from '../../types/project'
import MediaAsset from '../ui/MediaAsset'

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
   *  below the motion pane. */
  cascadeMetadata?: CascadeMetadata | null
  /** Lip-sync overlay cascade (NF-4, P1-3): dialogue takes carry a SECOND
   *  cascade record at take.metadata.lipsync_cascade — cascade_metadata on
   *  those takes holds the VIDEO cascade. Renders "lipsync via {engine}". */
  lipsyncCascadeMetadata?: CascadeMetadata | null
  /** Producer-level validation result. This remains separate from provider
   *  audio metadata because an audio-bearing clip is not sync evidence. */
  lipsyncValidationState?: LipsyncValidationState | string | null
  /** Used only to avoid showing a lip-sync gate for an explicitly
   *  non-dialogue native-audio take. Missing legacy applicability fails safe. */
  hasDialogue?: boolean
}

export function normalizeLipsyncValidationState(state: unknown): LipsyncValidationState {
  const normalized = typeof state === 'string' ? state.trim().toUpperCase() : ''
  if (normalized === 'PASS' || normalized === 'FAIL') return normalized
  return 'UNKNOWN'
}

/** A quality-evidence badge shared by live Monitor and persisted Review UI.
 *  `showWhenUnmeasured` is deliberately explicit: it lets native-audio and
 *  legacy cascade records surface UNKNOWN without inventing PASS from audio
 *  presence or a numeric threshold comparison. */
export function LipsyncStatusBadge({
  state,
  nativeAudioGenerated = false,
  showWhenUnmeasured = false,
}: {
  state?: LipsyncValidationState | string | null
  nativeAudioGenerated?: boolean | null
  showWhenUnmeasured?: boolean
}) {
  const hasState = typeof state === 'string' && state.trim().length > 0
  const showState = hasState || showWhenUnmeasured
  if (!showState && !nativeAudioGenerated) return null

  const normalizedState = normalizeLipsyncValidationState(state)
  const stateStyle = normalizedState === 'PASS'
    ? 'border-ok/40 bg-ok/10 text-ok'
    : normalizedState === 'FAIL'
      ? 'border-fail/40 bg-fail/10 text-fail'
      : 'border-warn/40 bg-warn/10 text-warn'
  const explanation = normalizedState === 'PASS'
    ? 'Lip-sync validation passed.'
    : normalizedState === 'FAIL'
      ? 'Lip-sync validation failed. Manual review is required.'
      : 'Lip-sync was not measured or could not be verified. Manual review is required.'

  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      {nativeAudioGenerated && (
        <span
          className="rounded border border-line bg-head px-1.5 py-0.5 text-eyebrow text-mut"
          title="The provider generated audio; audio presence is not lip-sync validation."
        >
          Native audio
        </span>
      )}
      {showState && (
        <span
          className={`rounded border px-1.5 py-0.5 text-eyebrow font-semibold ${stateStyle}`}
          role="status"
          aria-label={`Lip-sync validation: ${normalizedState}`}
          title={explanation}
        >
          Lip-sync {normalizedState}
        </span>
      )}
      {normalizedState === 'UNKNOWN' && showState && (
        <span className="text-eyebrow text-warn">Manual review required</span>
      )}
    </div>
  )
}

/** Engine/score/fallback chip row — shared by the video and lipsync rows. */
function CascadeChips({ meta, label }: { meta?: CascadeMetadata | null; label?: string }) {
  if (!meta) return null
  const isLipsync = label === 'lipsync'
  const scoreStyle = isLipsync
    ? meta.validation_state === 'PASS'
      ? 'text-ok'
      : meta.validation_state === 'FAIL'
        ? 'text-fail'
        : 'text-mut'
    : meta.score != null && meta.threshold != null && meta.score >= meta.threshold
      ? 'text-acc'
      : 'text-mut'
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      <span className="rounded bg-head px-1.5 py-0.5 text-eyebrow text-mut">
        {label ? `${label} via ${meta.engine}` : `via ${meta.engine}`}
      </span>
      {meta.score != null && meta.threshold != null && (
        <span className={`font-mono text-eyebrow ${scoreStyle}`}>
          {meta.score.toFixed(3)}
        </span>
      )}
      {meta.fallback && (
        <span className="rounded bg-acc/20 px-1.5 py-0.5 text-eyebrow text-acc">
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
  apiBase,
  projectId,
  labels,
  cascadeMetadata,
  lipsyncCascadeMetadata,
  lipsyncValidationState,
  hasDialogue,
}: TakeStripProps) {
  const hasAny = Boolean(keyframeUrl || drivingUrl || performanceUrl || motionUrl)
  if (!hasAny) return null

  // fileUrl defaults apiBase to '/api' itself (via `??`, matching Filmstrip's
  // convention) -- an explicit `= ''` default here would defeat that fallback
  // (`'' ?? '/api'` stays `''`, unlike the old `'' || '/api'` this replaces).
  const resolve = (path: string) => fileUrl(apiBase, projectId, path)

  const keyframeLabel = labels?.keyframe ?? 'Keyframe'
  const drivingLabel = labels?.driving ?? 'Driving reference'
  const performanceLabel = labels?.performance ?? 'Captured performance'
  const motionLabel = labels?.motion ?? 'Motion render'
  const nativeAudioGenerated = cascadeMetadata?.native_audio_generated === true
  const resolvedLipsyncState = lipsyncValidationState
    ?? lipsyncCascadeMetadata?.validation_state
    ?? cascadeMetadata?.validation_state
  const showUnmeasuredLipsync = hasDialogue === true
    || Boolean(lipsyncCascadeMetadata)
    || (nativeAudioGenerated && hasDialogue !== false)

  return (
    <div className="mt-3 grid gap-2 sm:grid-cols-2">
      {keyframeUrl ? (
        <div>
          <div className="text-eyebrow-lg uppercase text-mut mb-1">{keyframeLabel}</div>
          <MediaAsset
            kind="image"
            url={resolve(keyframeUrl)}
            className="w-full aspect-video rounded border border-line"
          />
        </div>
      ) : null}

      {drivingUrl ? (
        <div>
          <div className="text-eyebrow-lg uppercase text-mut mb-1">{drivingLabel}</div>
          <MediaAsset
            kind="video"
            url={resolve(drivingUrl)}
            className="w-full aspect-video rounded border border-line"
            controls
            muted
            loop
          />
        </div>
      ) : null}

      {performanceUrl ? (
        <div>
          <div className="text-eyebrow-lg uppercase text-mut mb-1">{performanceLabel}</div>
          <MediaAsset
            kind="video"
            url={resolve(performanceUrl)}
            className="w-full aspect-video rounded border border-line"
            controls
            muted
            loop
          />
        </div>
      ) : null}

      {motionUrl ? (
        <div>
          <div className="text-eyebrow-lg uppercase text-mut mb-1">{motionLabel}</div>
          <MediaAsset
            kind="video"
            url={resolve(motionUrl)}
            className="w-full aspect-video rounded border border-line"
            controls
            muted
            loop
          />
          <CascadeChips meta={cascadeMetadata} />
          <CascadeChips meta={lipsyncCascadeMetadata} label="lipsync" />
          <LipsyncStatusBadge
            state={resolvedLipsyncState}
            nativeAudioGenerated={nativeAudioGenerated}
            showWhenUnmeasured={showUnmeasuredLipsync}
          />
        </div>
      ) : null}
    </div>
  )
}
