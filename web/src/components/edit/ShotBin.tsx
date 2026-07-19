import type { Scene, ShotState } from '../../types/project'
import { StatusDot, MICRO_LABEL, type Status } from '../ui'
import { classifyShotType } from '../../lib/guidance'

interface Props {
  scene: Scene | null
  shotStates: Map<string, Partial<ShotState>>
  activeShotId: string | null
  onSelectShot: (shotId: string) => void
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
 */
export default function ShotBin({ scene, shotStates, activeShotId, onSelectShot }: Props) {
  const shots = scene?.shots ?? []

  return (
    <aside className="flex w-[220px] flex-none flex-col overflow-y-auto border-r border-line bg-gutter">
      <div className="flex flex-none items-center justify-between border-b border-line px-3 py-2">
        <span className={MICRO_LABEL}>Shot bin</span>
        <span className="font-mono text-[10px] text-dim">{shots.length}</span>
      </div>

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
            return (
              <li key={shot.id}>
                <button
                  type="button"
                  onClick={() => onSelectShot(shot.id)}
                  aria-current={active ? 'true' : undefined}
                  className={[
                    'flex w-full items-center gap-2 border-b border-line/60 px-3 py-2 text-left text-[11px] transition-colors',
                    active ? 'bg-panel text-tx' : 'text-mut hover:bg-panel/60 hover:text-tx',
                  ].join(' ')}
                >
                  <StatusDot status={DOT_STATUS[status] ?? 'idle'} />
                  <span className="font-mono text-dim">{String(i + 1).padStart(2, '0')}</span>
                  <span className="truncate capitalize">{classifyShotType(shot)}</span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </aside>
  )
}
