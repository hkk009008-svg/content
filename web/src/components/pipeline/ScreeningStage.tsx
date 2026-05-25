import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import type { Project, Shot, TakeRecord } from '../../types/project'
import IterationPanel from './IterationPanel'

/** S20 (cycle-9 Surface B): SCREENING stage UI — post-ASSEMBLY operator
 *  preview-and-iterate surface.
 *
 *  Flow:
 *  1. On mount, POST /api/projects/<pid>/assemble/screen to fetch the
 *     assembled mp4 path + per-shot timeline manifest (S19 substrate).
 *  2. Render an HTML5 <video> player using the mp4 served via the
 *     existing /api/projects/<pid>/file?path=... route (which returns
 *     video/mp4 inline; the /export route forces a download via
 *     as_attachment=True, so it's not usable for <video src>).
 *  3. Below the player, render a per-shot marker track using
 *     start_s/end_s from the manifest, normalised against the video's
 *     loadedmetadata duration (project-state estimates may drift from
 *     ffprobe-true; we re-render once the browser knows the truth).
 *  4. Click a marker → open the take-history sidebar AND seek the
 *     video to that shot's start_s.
 *  5. Sidebar shows all takes for the clicked shot, grouped by kind,
 *     with the approved final take highlighted. Each take has an
 *     "Iterate" button that reveals the existing IterationPanel
 *     (S18 substrate, used verbatim). target_stage is derived from
 *     take.kind: keyframe → 'keyframe', performance → 'performance',
 *     motion/postprocess → 'motion'.
 *  6. Bottom toolbar:
 *     - "Approve Final Cut" → POST /screening/approve, refresh project
 *     - "Re-assemble" → STUB (S21)
 *     - "Compare with previous cut" → STUB (S21+)
 *
 *  Palette: editorial-* only (ARCHITECTURE.md §14.3 invariant).
 *  Feature flag: gated server-side by CINEMA_SCREENING_STAGE; we surface
 *  the 404 as an inline error rather than guessing the flag client-side.
 */

interface ScreenManifestEntry {
  shot_id: string
  scene_id: string
  start_s: number
  end_s: number
  approved_take_id: string
  take_count: number
}

interface ScreenResponse {
  success: boolean
  assembled_mp4_path: string
  timeline_manifest: ScreenManifestEntry[]
  error?: string
}

interface Props {
  project: Project
  onApproveFinal: () => Promise<void>
  onIterate?: (
    shotId: string,
    takeId: string,
    prose: string,
    targetStage?: 'keyframe' | 'performance' | 'motion',
    verb?: string,
    params?: Record<string, unknown>,
  ) => Promise<any>
  onRefreshProject?: () => Promise<void> | void
}

/* ── Helpers ────────────────────────────────────────────────────── */

const formatTimecode = (seconds: number): string => {
  const safe = Math.max(0, seconds)
  const m = Math.floor(safe / 60)
  const s = Math.floor(safe % 60)
  const cs = Math.floor((safe - Math.floor(safe)) * 100)
  return `${m}:${s.toString().padStart(2, '0')}.${cs.toString().padStart(2, '0')}`
}

/** Resolve target_stage for the iterate endpoint from a take's kind.
 *  Production data stores performance takes with ``kind = "performance"``
 *  (see cinema/shots/controller.py:663 — ``make_take("performance", ...)``).
 *  The TakeRecord TypeScript union is narrower than the runtime values, so
 *  we widen via a string compare. Mapping:
 *    keyframe    → 'keyframe'
 *    performance → 'performance'
 *    motion      → 'motion'
 *    postprocess → 'motion'  (postprocess is a motion-stage refinement;
 *                              the iterate endpoint accepts 'motion'). */
const targetStageForTake = (
  take: TakeRecord,
): 'keyframe' | 'performance' | 'motion' => {
  const kind = take.kind as string
  if (kind === 'keyframe') return 'keyframe'
  if (kind === 'performance') return 'performance'
  return 'motion'
}

/** Per-shot collections to surface in the sidebar.
 *  Order = the operator's mental review chronology:
 *  keyframe (still) → performance (animated motion) → motion (final motion) → postprocess. */
interface TakeGroup {
  label: string
  kind: 'keyframe' | 'performance' | 'motion' | 'postprocess'
  takes: TakeRecord[]
}

const takeGroupsForShot = (shot: Shot): TakeGroup[] => {
  const groups: TakeGroup[] = []
  if (shot.keyframe_takes?.length) {
    groups.push({ label: 'Keyframe', kind: 'keyframe', takes: shot.keyframe_takes })
  }
  if (shot.performance_takes?.length) {
    groups.push({ label: 'Performance', kind: 'performance', takes: shot.performance_takes })
  }
  if (shot.motion_takes?.length) {
    groups.push({ label: 'Motion', kind: 'motion', takes: shot.motion_takes })
  }
  if (shot.postprocess_variants?.length) {
    groups.push({ label: 'Postprocess', kind: 'postprocess', takes: shot.postprocess_variants })
  }
  return groups
}

/* ── Sidebar take card ─────────────────────────────────────────── */

interface TakeCardProps {
  take: TakeRecord
  isApprovedFinal: boolean
  shotId: string
  onIterate?: Props['onIterate']
  onRefreshProject?: Props['onRefreshProject']
}

function TakeCard({ take, isApprovedFinal, shotId, onIterate, onRefreshProject }: TakeCardProps) {
  const [iterating, setIterating] = useState(false)

  const handleSubmit = useCallback(
    async (prose: string, verb?: string, params?: Record<string, unknown>) => {
      if (!onIterate) return { error: 'Iteration is not enabled.' }
      const result = await onIterate(
        shotId,
        take.id,
        prose,
        targetStageForTake(take),
        verb,
        params,
      )
      if (result?.success) {
        setIterating(false)
        if (onRefreshProject) await onRefreshProject()
      }
      return result
    },
    [onIterate, shotId, take, onRefreshProject],
  )

  return (
    <div
      className={`rounded border px-3 py-2 ${
        isApprovedFinal
          ? 'border-editorial-brass/60 bg-editorial-brass/5'
          : 'border-editorial-rule bg-editorial-ink-soft/40'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="font-mono text-eyebrow text-editorial-ivory-mute truncate">
            {take.id}
          </div>
          {take.created_at && (
            <div className="font-mono text-eyebrow-sm text-editorial-ivory-faint">
              {take.created_at}
            </div>
          )}
        </div>
        {isApprovedFinal && (
          <span className="font-mono text-eyebrow uppercase tracking-wide-eyebrow text-editorial-brass shrink-0">
            Final
          </span>
        )}
      </div>
      {onIterate && (
        <div className="mt-1.5">
          {!iterating ? (
            <button
              type="button"
              onClick={() => setIterating(true)}
              className="text-eyebrow text-editorial-brass hover:text-editorial-brass-deep"
            >
              Iterate this take →
            </button>
          ) : (
            <IterationPanel
              onSubmit={handleSubmit}
              onCancel={() => setIterating(false)}
            />
          )}
        </div>
      )}
    </div>
  )
}

/* ── Sidebar ───────────────────────────────────────────────────── */

interface SidebarProps {
  shot: Shot | null
  manifestEntry: ScreenManifestEntry | null
  onClose: () => void
  onIterate?: Props['onIterate']
  onRefreshProject?: Props['onRefreshProject']
}

function Sidebar({ shot, manifestEntry, onClose, onIterate, onRefreshProject }: SidebarProps) {
  if (!shot || !manifestEntry) {
    return (
      <div className="px-6 py-8 text-center">
        <p className="font-mono text-eyebrow uppercase tracking-wide-eyebrow text-editorial-ivory-faint">
          Click a shot marker to inspect its takes
        </p>
      </div>
    )
  }

  const groups = takeGroupsForShot(shot)
  const approvedId = shot.approved_final_take_id

  return (
    <div className="px-5 py-5 space-y-5">
      <div className="flex items-start justify-between gap-3 pb-3 border-b border-editorial-rule">
        <div>
          <div className="font-mono text-eyebrow uppercase tracking-wide-eyebrow text-editorial-ivory-mute">
            Shot
          </div>
          <div className="font-mono text-sm text-editorial-ivory">{shot.id}</div>
          <div className="mt-1 font-mono text-eyebrow-sm text-editorial-ivory-faint">
            {formatTimecode(manifestEntry.start_s)} – {formatTimecode(manifestEntry.end_s)}
            {' · '}
            {manifestEntry.take_count} take{manifestEntry.take_count === 1 ? '' : 's'}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close sidebar"
          className="text-editorial-ivory-mute hover:text-editorial-ivory text-sm"
        >
          ×
        </button>
      </div>

      {shot.prompt && (
        <div>
          <div className="font-mono text-eyebrow uppercase tracking-wide-eyebrow text-editorial-ivory-mute mb-1">
            Prompt
          </div>
          <p className="text-xs text-editorial-ivory-soft leading-relaxed">{shot.prompt}</p>
        </div>
      )}

      {groups.length === 0 ? (
        <p className="text-eyebrow text-editorial-ivory-faint">
          No takes recorded for this shot.
        </p>
      ) : (
        groups.map((group) => (
          <div key={group.kind}>
            <div className="font-mono text-eyebrow uppercase tracking-wide-eyebrow text-editorial-ivory-mute mb-2">
              {group.label} · {group.takes.length}
            </div>
            <div className="space-y-2">
              {group.takes.map((take) => (
                <TakeCard
                  key={take.id}
                  take={take}
                  isApprovedFinal={take.id === approvedId}
                  shotId={shot.id}
                  onIterate={onIterate}
                  onRefreshProject={onRefreshProject}
                />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  )
}

/* ── Timeline marker track ─────────────────────────────────────── */

interface MarkerTrackProps {
  manifest: ScreenManifestEntry[]
  totalDuration: number
  selectedShotId: string | null
  onSelect: (entry: ScreenManifestEntry) => void
}

function MarkerTrack({ manifest, totalDuration, selectedShotId, onSelect }: MarkerTrackProps) {
  if (manifest.length === 0 || totalDuration <= 0) {
    return (
      <div className="px-12 py-6">
        <div className="h-10 rounded border border-dashed border-editorial-rule flex items-center justify-center">
          <span className="font-mono text-eyebrow uppercase tracking-wide-eyebrow text-editorial-ivory-faint">
            No shot markers
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className="px-12 py-4">
      <div className="font-mono text-eyebrow uppercase tracking-wide-eyebrow text-editorial-ivory-mute mb-2 flex items-center justify-between">
        <span>Shot Markers · {manifest.length}</span>
        <span className="text-editorial-ivory-faint">
          {formatTimecode(totalDuration)} runtime
        </span>
      </div>
      <div className="relative h-10 bg-editorial-ink-soft border border-editorial-rule rounded overflow-hidden">
        {manifest.map((entry) => {
          const leftPct = Math.max(0, Math.min(100, (entry.start_s / totalDuration) * 100))
          const widthPct = Math.max(
            0.5,
            Math.min(100 - leftPct, ((entry.end_s - entry.start_s) / totalDuration) * 100),
          )
          const isSelected = entry.shot_id === selectedShotId
          return (
            <button
              key={entry.shot_id}
              type="button"
              onClick={() => onSelect(entry)}
              title={`${entry.shot_id} · ${formatTimecode(entry.start_s)} – ${formatTimecode(entry.end_s)}`}
              aria-label={`Shot ${entry.shot_id}, ${formatTimecode(entry.start_s)} to ${formatTimecode(entry.end_s)}`}
              className={`absolute top-0 bottom-0 border-l border-editorial-ink transition-colors ${
                isSelected
                  ? 'bg-editorial-brass/40 hover:bg-editorial-brass/60'
                  : 'bg-editorial-ivory-mute/15 hover:bg-editorial-ivory-mute/30'
              }`}
              style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
            >
              <span className="sr-only">{entry.shot_id}</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

/* ── Main ScreeningStage component ─────────────────────────────── */

export default function ScreeningStage({
  project,
  onApproveFinal,
  onIterate,
  onRefreshProject,
}: Props) {
  const [data, setData] = useState<ScreenResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedShotId, setSelectedShotId] = useState<string | null>(null)
  const [videoDuration, setVideoDuration] = useState<number>(0)
  const [approving, setApproving] = useState(false)
  const videoRef = useRef<HTMLVideoElement | null>(null)

  // ── Manifest fetch ──────────────────────────────────────────
  const fetchManifest = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/api/projects/${project.id}/assemble/screen`, {
        method: 'POST',
      })
      const json = (await res.json()) as ScreenResponse
      if (!res.ok || !json.success) {
        setError(json.error || `Could not load screening manifest (HTTP ${res.status}).`)
        setData(null)
      } else {
        setData(json)
      }
    } catch {
      setError('Network error while fetching the screening manifest.')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [project.id])

  useEffect(() => {
    fetchManifest()
  }, [fetchManifest])

  // ── Index shots from project by id for sidebar lookups ──────
  const shotIndex = useMemo(() => {
    const index = new Map<string, Shot>()
    for (const scene of project.scenes) {
      for (const shot of scene.shots ?? []) {
        index.set(shot.id, shot)
      }
    }
    return index
  }, [project.scenes])

  // ── Effective video duration: ffprobe-true if known, manifest fallback ──
  const manifestTotal = useMemo(() => {
    if (!data?.timeline_manifest?.length) return 0
    return data.timeline_manifest[data.timeline_manifest.length - 1].end_s
  }, [data])

  const effectiveDuration = videoDuration > 0 ? videoDuration : manifestTotal

  // ── Marker click handler: select + seek ─────────────────────
  const handleSelectMarker = useCallback((entry: ScreenManifestEntry) => {
    setSelectedShotId(entry.shot_id)
    if (videoRef.current) {
      try {
        videoRef.current.currentTime = entry.start_s
      } catch {
        /* ignore seek errors (e.g. metadata not loaded yet) */
      }
    }
  }, [])

  // ── Approve final cut ───────────────────────────────────────
  const handleApprove = useCallback(async () => {
    if (approving) return
    const confirmed = window.confirm(
      'Approve final cut? The pipeline will finalise this assembly and exit.',
    )
    if (!confirmed) return
    setApproving(true)
    try {
      await onApproveFinal()
    } finally {
      setApproving(false)
    }
  }, [approving, onApproveFinal])

  const selectedManifestEntry = useMemo(() => {
    if (!data || !selectedShotId) return null
    return data.timeline_manifest.find((e) => e.shot_id === selectedShotId) ?? null
  }, [data, selectedShotId])

  const selectedShot = selectedShotId ? shotIndex.get(selectedShotId) ?? null : null

  // ── Render: loading ─────────────────────────────────────────
  if (loading) {
    return (
      <div className="py-24 text-center">
        <div className="inline-flex items-center gap-3 text-editorial-ivory-mute">
          <span className="inline-block h-3 w-3 rounded-full bg-editorial-brass animate-pulse" />
          <span className="font-mono text-eyebrow uppercase tracking-wide-eyebrow">
            Loading screening manifest…
          </span>
        </div>
      </div>
    )
  }

  // ── Render: error ───────────────────────────────────────────
  if (error || !data) {
    return (
      <div className="mt-6 mx-12 rounded border border-editorial-curtain/40 bg-editorial-curtain/10 px-6 py-5">
        <div className="font-mono text-eyebrow uppercase tracking-wide-eyebrow text-editorial-curtain mb-2">
          Screening Unavailable
        </div>
        <p className="text-sm text-editorial-ivory-soft mb-3">
          {error || 'No data returned from /assemble/screen.'}
        </p>
        <p className="text-eyebrow text-editorial-ivory-mute mb-4">
          If the screening stage is not enabled (CINEMA_SCREENING_STAGE), this gate
          will be skipped. Restart the pipeline with the flag set, or proceed without
          screening.
        </p>
        <button
          type="button"
          onClick={fetchManifest}
          className="rounded border border-editorial-rule px-3 py-1.5 text-xs text-editorial-ivory hover:bg-editorial-ink-rise"
        >
          Retry
        </button>
      </div>
    )
  }

  // Build the file-server URL for the assembled mp4. The /file endpoint
  // security-checks containment within the project directory, so passing
  // the absolute path returned by /assemble/screen is correct.
  const videoSrc = `/api/projects/${project.id}/file?path=${encodeURIComponent(
    data.assembled_mp4_path,
  )}`

  return (
    <div className="grid grid-cols-[1fr_360px] gap-0 -mx-8 -my-6 min-h-0 h-full">
      {/* ── Left: video + markers + toolbar ──────────────────────── */}
      <div className="flex flex-col bg-editorial-ink overflow-y-auto">
        <div className="px-12 pt-8">
          <div className="font-mono text-eyebrow uppercase tracking-wide-eyebrow text-editorial-brass mb-3">
            Screening
          </div>
          <h2
            className="font-display italic text-editorial-ivory mb-5"
            style={{
              fontSize: 'clamp(28px, 3vw, 44px)',
              fontVariationSettings: '"opsz" 48, "SOFT" 60, "WONK" 1',
              lineHeight: 1,
              letterSpacing: '-0.01em',
            }}
          >
            Review the cut
          </h2>
        </div>

        <div className="px-12">
          <div className="bg-black rounded border border-editorial-rule overflow-hidden">
            <video
              ref={videoRef}
              src={videoSrc}
              controls
              playsInline
              preload="metadata"
              onLoadedMetadata={(e) => {
                const v = e.currentTarget
                if (Number.isFinite(v.duration) && v.duration > 0) {
                  setVideoDuration(v.duration)
                }
              }}
              className="w-full max-h-[60vh] bg-black"
            />
          </div>
        </div>

        <MarkerTrack
          manifest={data.timeline_manifest}
          totalDuration={effectiveDuration}
          selectedShotId={selectedShotId}
          onSelect={handleSelectMarker}
        />

        {/* Bottom toolbar */}
        <div className="px-12 py-6 mt-auto border-t border-editorial-rule flex items-center justify-between gap-4 flex-wrap">
          <div className="font-mono text-eyebrow uppercase tracking-wide-eyebrow text-editorial-ivory-mute">
            {data.timeline_manifest.length} shots in cut
            {selectedShot && (
              <>
                {' · '}
                <span className="text-editorial-ivory">selected {selectedShot.id}</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled
              title="Available in S21"
              className="rounded border border-editorial-rule px-3 py-2 text-xs text-editorial-ivory-faint cursor-not-allowed"
            >
              Compare with previous cut
            </button>
            <button
              type="button"
              disabled
              title="Available in S21"
              className="rounded border border-editorial-rule px-3 py-2 text-xs text-editorial-ivory-faint cursor-not-allowed"
            >
              Re-assemble
            </button>
            <button
              type="button"
              onClick={handleApprove}
              disabled={approving}
              className="rounded bg-editorial-brass px-4 py-2 text-xs font-semibold text-white hover:bg-editorial-brass/90 disabled:opacity-40"
            >
              {approving ? 'Approving…' : 'Approve Final Cut'}
            </button>
          </div>
        </div>
      </div>

      {/* ── Right: take-history sidebar ──────────────────────── */}
      <aside className="border-l border-editorial-rule bg-editorial-ink-soft/30 overflow-y-auto">
        <Sidebar
          shot={selectedShot}
          manifestEntry={selectedManifestEntry}
          onClose={() => setSelectedShotId(null)}
          onIterate={onIterate}
          onRefreshProject={onRefreshProject}
        />
      </aside>
    </div>
  )
}
