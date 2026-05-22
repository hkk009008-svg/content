import { useMemo } from 'react'
import TakeStrip from './TakeStrip'
import type { Project, ShotState, DirectorReview } from '../../types/project'

export interface MonitorProps {
  project: Project
  activeShotId: string | null
  shotStates: Map<string, Partial<ShotState>>
  apiBase?: string
  projectId?: string | null
  directorReview: DirectorReview | null
}

export default function Monitor({
  project,
  activeShotId,
  shotStates,
  apiBase,
  projectId,
  directorReview,
}: MonitorProps) {
  const activeState = useMemo(
    () => (activeShotId ? shotStates.get(activeShotId) : null),
    [activeShotId, shotStates]
  )

  const keyframeUrl = activeState?.generated_image ?? null
  const videoUrl = activeState?.generated_video ?? null

  // Attempt to distinguish motion vs performance from take_kind
  const takeKind = activeState?.take_kind
  const performanceUrl = takeKind === 'performance' ? videoUrl : null
  const motionUrl = takeKind === 'motion' || (!takeKind && videoUrl) ? videoUrl : null

  return (
    <main className="col-span-7 px-6 py-6">
      <h2 className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute mb-3">
        Monitor
      </h2>

      {keyframeUrl || performanceUrl || motionUrl ? (
        <TakeStrip
          keyframeUrl={keyframeUrl}
          performanceUrl={performanceUrl}
          motionUrl={motionUrl}
          apiBase={apiBase}
          projectId={projectId}
        />
      ) : (
        <div className="aspect-video rounded border border-editorial-rule bg-editorial-ink flex items-center justify-center">
          <div className="text-center text-xs text-editorial-ivory-mute">
            {activeShotId ? 'Waiting for first take…' : 'No active shot'}
          </div>
        </div>
      )}

      {directorReview && (
        <div className="mt-4 rounded border border-editorial-brass/30 bg-editorial-brass/5 px-4 py-3">
          <div className={`text-eyebrow-lg uppercase tracking-wider font-semibold ${
            directorReview.decision === 'APPROVED'
              ? 'text-editorial-ready'
              : directorReview.decision === 'REJECTED'
                ? 'text-editorial-curtain'
                : 'text-editorial-brass'
          }`}>
            Director Review · {directorReview.decision}
            {directorReview.quality_score != null && (
              <span className="ml-2 font-normal">
                ({Math.round(directorReview.quality_score * 100)}%)
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-editorial-ivory-mute">{directorReview.reasoning}</p>
          {directorReview.violations.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs text-editorial-curtain">
              {directorReview.violations.map((v, i) => <li key={i}>{v}</li>)}
            </ul>
          )}
        </div>
      )}
    </main>
  )
}
