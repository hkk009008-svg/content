import type { Project, ShotState } from '../../types/project'
import { StatusDot, type Status } from '../ui'

interface Props {
  project: Project
  shotStates: Map<string, Partial<ShotState>>
  activeShotId: string | null
  onSelect: (shotId: string) => void
}

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
 * Timeline — the canonical "scenes -> shots as clips" horizontal track.
 * ALL `project.scenes` (not just the focused one) render as labeled groups,
 * each holding its shots as clips in scene order. Clicking (or
 * double-clicking — it never navigates away, so the edit stays put) a clip
 * selects that shot; the currently-active clip is highlighted with
 * `border-acc`.
 */
export default function Timeline({ project, shotStates, activeShotId, onSelect }: Props) {
  const scenes = [...project.scenes].sort((a, b) => a.order - b.order)

  return (
    <div className="flex-none border-t border-line bg-gutter">
      <div className="overflow-x-auto">
        <div className="flex items-stretch gap-4 px-3 py-2">
          {scenes.map((scene) => {
            const shots = scene.shots ?? []
            return (
              <div key={scene.id} className="flex flex-none flex-col gap-1">
                <span className="max-w-[200px] truncate font-mono text-[9px] uppercase tracking-wide text-dim">
                  {scene.title || 'Untitled scene'}
                </span>
                <div className="flex gap-1" role="group" aria-label={scene.title || 'Untitled scene'}>
                  {shots.length === 0 ? (
                    <div className="flex h-10 w-16 flex-none items-center justify-center rounded border border-line/50 font-mono text-[10px] text-dim">
                      —
                    </div>
                  ) : (
                    shots.map((shot, i) => {
                      const state = shotStates.get(shot.id)
                      const status = state?.status ?? 'pending'
                      const selected = shot.id === activeShotId
                      return (
                        <button
                          key={shot.id}
                          type="button"
                          data-shot-id={shot.id}
                          onClick={() => onSelect(shot.id)}
                          onDoubleClick={() => onSelect(shot.id)}
                          aria-current={selected ? 'true' : undefined}
                          title={shot.prompt?.slice(0, 80)}
                          className={[
                            'flex h-10 w-16 flex-none flex-col items-center justify-center gap-0.5 rounded border font-mono text-[10px] transition-colors',
                            selected ? 'border-acc text-tx' : 'border-line text-mut hover:text-tx',
                          ].join(' ')}
                        >
                          <StatusDot status={DOT_STATUS[status] ?? 'idle'} />
                          <span>{i + 1}</span>
                        </button>
                      )
                    })
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
