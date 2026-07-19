import { useEffect, useMemo, useState } from 'react'
import type { Project, Shot, ShotState } from '../../types/project'
import { fileUrl } from '../../lib/mediaUrl'
import { MICRO_LABEL } from '../ui'

/**
 * Filmstrip — the single canonical shot reel, merging the two prior copies:
 *   - `pipeline/Filmstrip` (4-state `frameStatusOf(ShotState.status)` + engine tag)
 *   - `console/Filmstrip`  (windowed 40 + "+N more", real `generated_image` thumbnails,
 *                            click-to-select nav)
 *
 * Status resolution: when a live `ShotState` exists for a shot, its 4-state
 * frame status wins (`frameStatusOf`); otherwise we fall back to the persisted
 * `shot.plan_status` (2-state: approved → done, rejected → failed, else pending).
 * Both status models reconcile onto the same `FrameStatus` union — no backend
 * data change required.
 *
 * New file: design tokens only (bg-panel, border-line, text-acc/-ok/-warn/-fail).
 */

const FILMSTRIP_WINDOW = 40

type FrameStatus = 'done' | 'active' | 'pending' | 'failed'

/** Map a live ShotStatus onto the coarse 4-state frame status the strip cares
 *  about. Ported verbatim from the former `pipeline/Filmstrip`. */
function frameStatusOf(status: ShotState['status'] | undefined): FrameStatus {
  if (!status) return 'pending'
  if (status === 'failed') return 'failed'
  if (status === 'complete' || status === 'post_processing' || status === 'image_review') {
    return 'done'
  }
  if (
    status === 'generating_image' ||
    status === 'generating_video' ||
    status === 'plan_review' ||
    status === 'final_review'
  ) {
    return 'active'
  }
  return 'pending'
}

/** Fall back to the persisted plan_status when no live ShotState exists. */
function planStatusFrame(planStatus: Shot['plan_status'] | undefined): FrameStatus {
  if (planStatus === 'approved') return 'done'
  if (planStatus === 'rejected') return 'failed'
  return 'pending'
}

/** Short engine tag (Veo, Kling, Sora, …) from a target_api string. */
function engineTag(targetApi: string | undefined, status: FrameStatus): string {
  if (status === 'active') return 'Live'
  if (status === 'pending') return '—'
  if (!targetApi) return '—'
  const head = targetApi.split(/[_-]/)[0] ?? targetApi
  return head.charAt(0).toUpperCase() + head.slice(1).toLowerCase()
}

const pad2 = (n: number) => n.toString().padStart(2, '0')

/** Per-status border/ring tone (design tokens only). Active shot overrides. */
const STATUS_BORDER: Record<FrameStatus, string> = {
  done: 'border-ok/50',
  active: 'border-pri',
  failed: 'border-fail',
  pending: 'border-line',
}

interface FrameEntry {
  shot: Shot
  index: number // project-wide, 1-based
  status: FrameStatus
}

export interface FilmstripProps {
  project: Project
  /** Live shot states from the pipeline. Optional — absent on the passive
   *  monitor surfaces, where every shot falls back to plan_status. */
  shotStates?: Map<string, Partial<ShotState>>
  apiBase?: string
  projectId?: string | null
  activeShotId?: string | null
  onShotClick?: (shotId: string) => void
}

export default function Filmstrip({
  project,
  shotStates,
  apiBase,
  projectId,
  activeShotId,
  onShotClick,
}: FilmstripProps) {
  const [visibleCount, setVisibleCount] = useState(FILMSTRIP_WINDOW)

  // Reset the window when the project changes (console/Filmstrip behavior).
  useEffect(() => {
    setVisibleCount(FILMSTRIP_WINDOW)
  }, [projectId])

  // Flatten scenes → shots in playback (scene.order) order, assigning each a
  // project-wide 1-based index and resolving its frame status.
  const frames: FrameEntry[] = useMemo(() => {
    const ordered = project.scenes.slice().sort((a, b) => a.order - b.order)
    let runningIndex = 0
    const out: FrameEntry[] = []
    for (const scene of ordered) {
      for (const shot of scene.shots ?? []) {
        runningIndex += 1
        const state = shotStates?.get(shot.id)
        const status = state?.status
          ? frameStatusOf(state.status)
          : planStatusFrame(shot.plan_status)
        out.push({ shot, index: runningIndex, status })
      }
    }
    return out
  }, [project.scenes, shotStates])

  const visible = frames.slice(0, visibleCount)
  const overflow = frames.length - visibleCount

  const doneCount = frames.filter((f) => f.status === 'done').length
  const activeCount = frames.filter((f) => f.status === 'active').length

  const sceneTitleOf = (shotId: string) =>
    project.scenes.find((s) => s.shots?.some((sh) => sh.id === shotId))?.title ?? ''

  return (
    <section className="border-b border-line px-4 py-4">
      <div className="mb-3 flex items-center justify-between">
        <span className={MICRO_LABEL}>Filmstrip · All Shots</span>
        <span className="flex gap-3 font-mono text-[10px] uppercase tracking-[0.09em] tabular-nums text-dim">
          <span>{pad2(doneCount)} done</span>
          {activeCount > 0 && <span className="text-pri">{pad2(activeCount)} live</span>}
          <span>{pad2(frames.length)} total</span>
        </span>
      </div>

      <div className="overflow-x-auto">
        <div className="flex gap-1.5 bg-gutter p-2">
          {visible.map((frame) => {
            const { shot, index, status } = frame
            const isActiveShot = activeShotId != null && shot.id === activeShotId
            const img = shot.generated_image
            return (
              <button
                key={shot.id}
                type="button"
                data-shot-id={shot.id}
                data-status={status}
                onClick={() => onShotClick?.(shot.id)}
                title={shot.prompt?.slice(0, 80)}
                className={[
                  'group relative w-24 flex-none aspect-[9/16] overflow-hidden rounded border bg-panel',
                  'cursor-pointer transition-all hover:-translate-y-0.5',
                  `status-${status}`,
                  isActiveShot
                    ? 'border-acc shadow-[0_0_0_1px_var(--acc)]'
                    : STATUS_BORDER[status],
                  status === 'pending' ? 'opacity-60' : '',
                ].join(' ')}
              >
                {img ? (
                  <img
                    src={fileUrl(apiBase, projectId, img)}
                    className="h-full w-full object-cover"
                    alt=""
                  />
                ) : (
                  <div className="flex h-full w-full items-center justify-center bg-head text-[9px] font-mono uppercase tracking-[0.09em] text-dim">
                    no take
                  </div>
                )}

                {/* Shot number — top left */}
                <span className="absolute left-1 top-1 z-10 rounded bg-black/70 px-1 py-px font-mono text-[8px] tracking-[0.12em] text-tx">
                  {pad2(index)}
                </span>

                {/* Engine tag — top right */}
                <span
                  className={[
                    'absolute right-1 top-1 z-10 rounded bg-black/70 px-1 py-px font-mono text-[7px] uppercase tracking-[0.14em]',
                    status === 'active' ? 'text-pri' : status === 'pending' ? 'text-dim' : 'text-mut',
                  ].join(' ')}
                >
                  {engineTag(shot.target_api, status)}
                </span>

                {/* Scene title — bottom scrim */}
                <span className="absolute inset-x-0 bottom-0 z-10 truncate bg-gradient-to-t from-black/90 to-transparent px-1 pb-0.5 pt-3 font-mono text-[8px] text-tx">
                  {sceneTitleOf(shot.id).slice(0, 12)}
                </span>
              </button>
            )
          })}

          {overflow > 0 && (
            <button
              type="button"
              onClick={() => setVisibleCount((v) => v + FILMSTRIP_WINDOW)}
              className="flex w-24 flex-none aspect-[9/16] items-center justify-center rounded border border-line bg-panel font-mono text-[10px] uppercase tracking-[0.09em] text-mut hover:border-acc hover:text-tx"
            >
              +{overflow} more
            </button>
          )}
        </div>
      </div>
    </section>
  )
}
