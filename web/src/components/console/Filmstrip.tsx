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
  if (!status) return 'bg-editorial-ivory-mute/20 text-editorial-ivory-mute'
  if (status === 'complete') return 'bg-editorial-ready/20 text-editorial-ready'
  if (status === 'failed') return 'bg-editorial-curtain/20 text-editorial-curtain'
  return 'bg-editorial-brass/20 text-editorial-brass'
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
    <section className="px-6 py-6 border-b border-editorial-rule">
      <h2 className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute mb-3">
        Filmstrip
      </h2>
      <div className="overflow-x-auto">
        <div className="flex gap-2">
          {visible.map((shot) => (
            <button
              key={shot.id}
              onClick={() => onShotClick?.(shot.id)}
              className="shrink-0 w-32 aspect-video rounded border border-editorial-rule bg-editorial-ink relative overflow-hidden cursor-pointer hover:border-editorial-brass/50 transition-colors"
              title={shot.prompt?.slice(0, 80)}
            >
              {shot.generated_image ? (
                <img
                  src={resolveImg(shot.generated_image)}
                  className="w-full h-full object-cover"
                  alt=""
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-xs text-editorial-ivory-mute">
                  no take
                </div>
              )}
              <div className="absolute bottom-0 left-0 right-0 bg-editorial-ink/80 px-1 py-0.5 flex items-center justify-between gap-1">
                <span className="text-eyebrow-lg text-editorial-ivory-mute truncate">
                  {sceneTitle(shot.id).slice(0, 10)}
                </span>
                <span className={`text-eyebrow-lg rounded px-1 shrink-0 ${statusBadgeClass(shot.plan_status === 'approved' ? 'complete' : undefined)}`}>
                  {statusLabel(shot.plan_status === 'approved' ? 'complete' : shot.plan_status === 'rejected' ? 'failed' : undefined)}
                </span>
              </div>
            </button>
          ))}
          {overflow > 0 && (
            <button
              onClick={() => setVisibleCount(v => v + FILMSTRIP_WINDOW)}
              className="shrink-0 w-32 aspect-video rounded border border-editorial-rule bg-editorial-ink flex items-center justify-center text-xs text-editorial-ivory-mute hover:border-editorial-brass/50 transition-colors cursor-pointer"
            >
              +{overflow} more
            </button>
          )}
        </div>
      </div>
    </section>
  )
}
