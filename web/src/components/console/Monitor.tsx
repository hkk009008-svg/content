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
      <h2 className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute mb-3 font-console-mono">
        Monitor
      </h2>

      {keyframeUrl || performanceUrl || motionUrl ? (
        <div className="shadow-console-viewport rounded border border-console-rule-strong overflow-hidden">
          <TakeStrip
            keyframeUrl={keyframeUrl}
            performanceUrl={performanceUrl}
            motionUrl={motionUrl}
            apiBase={apiBase}
            projectId={projectId}
          />
        </div>
      ) : (
        <div className="aspect-video rounded border border-console-rule-strong bg-console-render-fill shadow-console-viewport flex items-center justify-center">
          <div className="text-center text-xs text-console-ink-mute font-console-mono">
            {activeShotId ? 'Waiting for first take…' : 'No active shot'}
          </div>
        </div>
      )}

      {directorReview && (
        <div className="mt-4 rounded border border-console-gold/30 bg-console-surface-2 px-4 py-3">
          <div className={`text-eyebrow-lg uppercase tracking-wider font-semibold font-console-mono ${
            directorReview.decision === 'APPROVED'
              ? 'text-console-gold'
              : directorReview.decision === 'REJECTED'
                ? 'text-console-accent'
                : 'text-console-gold'
          }`}>
            Director Review · {directorReview.decision}
            {directorReview.quality_score != null && (
              <span className="ml-2 font-normal">
                ({Math.round(directorReview.quality_score * 100)}%)
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-console-ink-dim font-display italic">{directorReview.reasoning}</p>
          {directorReview.violations.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs text-console-accent font-console-mono">
              {directorReview.violations.map((v, i) => <li key={i}>{v}</li>)}
            </ul>
          )}
        </div>
      )}
    </main>
  )
}
