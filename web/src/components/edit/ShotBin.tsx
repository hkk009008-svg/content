import { useState } from 'react'
import type { Scene, ShotState } from '../../types/project'
import { StatusDot, LiveRegion, MICRO_LABEL, type Status } from '../ui'
import { classifyShotType } from '../../lib/guidance'
import { apiPut } from '../../lib/api'

interface Props {
  scene: Scene | null
  shotStates: Map<string, Partial<ShotState>>
  activeShotId: string | null
  onSelectShot: (shotId: string) => void
  projectId: string
  apiBase?: string
  onRefreshProject: () => Promise<void> | void
}

/** Coarse ShotStatus -> StatusDot tone. No run exists yet -> `idle` per the
 *  brief ("status from `shotStates` map when a run exists, else `idle`"). */
const DOT_STATUS: Record<string, Status> = {
  pending: 'idle',
  plan_review: 'warn',
  generating_image: 'run',
  image_review: 'warn',
  generating_video: 'run',
  final_review: 'warn',
  post_processing: 'run',
  complete: 'ok',
  failed: 'fail',
}

/**
 * ShotBin — left rail of the Edit workspace. Lists the focused scene's shots
 * (NOT the whole project — that's the Timeline's job) with a per-shot
 * `<StatusDot/>` sourced from the `shotStates` map when a run exists.
 *
 * Reorder (slice 13c): "Move earlier"/"Move later" buttons swap a shot with
 * its neighbor and PUT the scene's full `shots` array back in the new order
 * — the exact round-trip `ScenePanel` already uses for its own scene-reorder
 * and per-shot field edits (`PUT /api/projects/{pid}/scenes/{sid}` with
 * `{shots: [...]}`; the backend preserves list order and grandfathers each
 * shot's unchanged `target_api` since it's the same value, just relocated).
 * Real `<button>`s, not a drag handle, so the operation is keyboard-operable
 * (Tab + Enter/Space) from the start — no separate keyboard fallback needed.
 * A failed PUT surfaces through the shared `LiveRegion` primitive (visible +
 * announced), never console-only, and never silently reorders the on-screen
 * list ahead of backend confirmation.
 */
export default function ShotBin({
  scene,
  shotStates,
  activeShotId,
  onSelectShot,
  projectId,
  apiBase,
  onRefreshProject,
}: Props) {
  const shots = scene?.shots ?? []
  const base = apiBase || '/api'
  const [reorderError, setReorderError] = useState<string | null>(null)
  const [movingId, setMovingId] = useState<string | null>(null)

  const moveShot = async (index: number, direction: -1 | 1) => {
    if (!scene) return
    const targetIndex = index + direction
    if (targetIndex < 0 || targetIndex >= shots.length) return

    const reordered = shots.slice()
    ;[reordered[index], reordered[targetIndex]] = [reordered[targetIndex], reordered[index]]

    setReorderError(null)
    setMovingId(shots[index].id)
    const result = await apiPut(`${base}/projects/${projectId}/scenes/${scene.id}`, { shots: reordered })
    setMovingId(null)

    if (!result.ok) {
      setReorderError(result.error)
      return
    }
    await onRefreshProject()
  }

  return (
    <aside className="flex w-[220px] flex-none flex-col overflow-y-auto border-r border-line bg-gutter">
      <div className="flex flex-none items-center justify-between border-b border-line px-3 py-2">
        <span className={MICRO_LABEL}>Shot bin</span>
        <span className="font-mono text-[10px] text-dim">{shots.length}</span>
      </div>

      {reorderError && (
        <LiveRegion
          politeness="assertive"
          visuallyHidden={false}
          message={`Could not reorder: ${reorderError}`}
          className="border-b border-fail/50 bg-fail/10 px-3 py-2 text-[11px] text-fail"
        />
      )}

      {!scene ? (
        <p className="px-3 py-4 text-[11px] italic text-dim">No scene selected.</p>
      ) : shots.length === 0 ? (
        <p className="px-3 py-4 text-[11px] italic text-dim">No shots in this scene yet.</p>
      ) : (
        <ul>
          {shots.map((shot, i) => {
            const state = shotStates.get(shot.id)
            const status = state?.status ?? 'pending'
            const active = shot.id === activeShotId
            const label = classifyShotType(shot)
            const busy = movingId !== null
            const isFirst = i === 0
            const isLast = i === shots.length - 1
            return (
              <li key={shot.id} className="flex items-center border-b border-line/60">
                <button
                  type="button"
                  onClick={() => onSelectShot(shot.id)}
                  aria-current={active ? 'true' : undefined}
                  className={[
                    'flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left text-[11px] transition-colors',
                    active ? 'bg-panel text-tx' : 'text-mut hover:bg-panel/60 hover:text-tx',
                  ].join(' ')}
                >
                  <StatusDot status={DOT_STATUS[status] ?? 'idle'} />
                  <span className="font-mono text-dim">{String(i + 1).padStart(2, '0')}</span>
                  <span className="truncate capitalize">{label}</span>
                </button>
                <div className="flex flex-none items-center gap-0.5 pr-2">
                  <button
                    type="button"
                    onClick={() => moveShot(i, -1)}
                    disabled={isFirst || busy}
                    aria-label={`Move shot ${i + 1} (${label}) earlier in the scene`}
                    title={isFirst ? 'Already first in the scene' : 'Move earlier in the scene'}
                    className="rounded px-1 font-mono text-[10px] leading-none text-mut hover:text-acc disabled:opacity-30 disabled:hover:text-mut"
                  >
                    ▲
                  </button>
                  <button
                    type="button"
                    onClick={() => moveShot(i, 1)}
                    disabled={isLast || busy}
                    aria-label={`Move shot ${i + 1} (${label}) later in the scene`}
                    title={isLast ? 'Already last in the scene' : 'Move later in the scene'}
                    className="rounded px-1 font-mono text-[10px] leading-none text-mut hover:text-acc disabled:opacity-30 disabled:hover:text-mut"
                  >
                    ▼
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </aside>
  )
}
