import { useEffect, useState } from 'react'
import type { Project } from '../../types/project'

export interface FilmstripProps {
  project: Project
  apiBase?: string
  projectId: string | null
  onShotClick?: (shotId: string) => void
}

const FILMSTRIP_WINDOW = 40

function statusBadgeClass(status?: string): string {
  if (!status) return 'bg-console-ink-deep/40 text-console-ink-mute'
  if (status === 'complete') return 'bg-console-gold/20 text-console-gold'
  if (status === 'failed') return 'bg-console-accent/20 text-console-accent'
  return 'bg-console-gold/20 text-console-gold'
}

function statusLabel(status?: string): string {
  if (!status || status === 'pending') return 'pending'
  if (status === 'complete') return 'approved'
  if (status === 'failed') return 'failed'
  return 'in-progress'
}

export default function Filmstrip({ project, apiBase = '', projectId, onShotClick }: FilmstripProps) {
  const [visibleCount, setVisibleCount] = useState(FILMSTRIP_WINDOW)

  useEffect(() => {
    setVisibleCount(FILMSTRIP_WINDOW)
  }, [projectId])

  const base = apiBase || '/api'

  const allShots = project?.scenes?.flatMap(s => s.shots || []) || []
  const visible = allShots.slice(0, visibleCount)
  const overflow = allShots.length - visibleCount

  const resolveImg = (path: string) =>
    projectId
      ? `${base}/projects/${projectId}/file?path=${encodeURIComponent(path)}`
      : path

  const sceneTitle = (shotId: string) =>
    project?.scenes?.find(s => s.shots?.some(sh => sh.id === shotId))?.title || ''

  return (
    <section className="px-6 py-6 border-b border-console-rule">
      <h2 className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute mb-3 font-console-mono">
        Filmstrip
      </h2>
      <div className="filmstrip-scroll overflow-x-auto shadow-console-filmstrip-inset">
        <div className="flex gap-2 bg-black py-4 px-2">
          {visible.map((shot) => {
            const isDone = shot.plan_status === 'approved'
            const isFailed = shot.plan_status === 'rejected'
            return (
              <button
                key={shot.id}
                onClick={() => onShotClick?.(shot.id)}
                className={`shrink-0 w-32 aspect-video rounded border bg-console-surface relative overflow-hidden cursor-pointer transition-all ${
                  isFailed
                    ? 'border-console-accent shadow-console-frame-active'
                    : isDone
                      ? 'border-console-gold/50 hover:border-console-gold'
                      : 'border-transparent hover:border-console-gold/50'
                }`}
                title={shot.prompt?.slice(0, 80)}
              >
                {shot.generated_image ? (
                  <img
                    src={resolveImg(shot.generated_image)}
                    className="w-full h-full object-cover"
                    alt=""
                  />
                ) : (
                  <div className="w-full h-full bg-console-render-fill flex items-center justify-center text-xs text-console-ink-mute font-console-mono">
                    no take
                  </div>
                )}
                <div className="absolute bottom-0 left-0 right-0 bg-console-frame-scrim px-1 py-0.5 flex items-center justify-between gap-1">
                  <span className="text-eyebrow-lg text-console-ink truncate font-console-mono">
                    {sceneTitle(shot.id).slice(0, 10)}
                  </span>
                  <span className={`text-eyebrow-lg rounded px-1 shrink-0 font-console-mono ${statusBadgeClass(isDone ? 'complete' : isFailed ? 'failed' : undefined)}`}>
                    {statusLabel(isDone ? 'complete' : isFailed ? 'failed' : undefined)}
                  </span>
                </div>
              </button>
            )
          })}
          {overflow > 0 && (
            <button
              onClick={() => setVisibleCount(v => v + FILMSTRIP_WINDOW)}
              className="shrink-0 w-32 aspect-video rounded border border-console-rule-strong bg-console-surface flex items-center justify-center text-xs text-console-ink-mute hover:border-console-gold/50 transition-colors cursor-pointer font-console-mono"
            >
              +{overflow} more
            </button>
          )}
        </div>
      </div>
    </section>
  )
}
