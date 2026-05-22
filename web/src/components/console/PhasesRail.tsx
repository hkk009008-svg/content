import type { PipelineStage } from '../../types/project'

export interface PhasesRailProps {
  stages: PipelineStage[]
  activeStage: string | null
  isPaused: boolean
  failedShots: string[]
}

export default function PhasesRail({ stages, activeStage, isPaused, failedShots }: PhasesRailProps) {
  return (
    <aside className="col-span-2 border-r border-console-rule px-4 py-6 bg-console-surface flex flex-col">
      <h2 className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute mb-3 font-console-mono tracking-wide-eyebrow">
        Phases
      </h2>
      <ul className="text-xs flex-1 divide-y divide-console-rule">
        {stages.map((stage) => {
          const isActive = stage.id === activeStage
          const isDone = stage.status === 'complete'
          const isFailed = stage.status === 'failed'
          return (
            <li
              key={stage.id}
              className={`flex items-center gap-2 py-3 px-0 transition-colors ${
                isActive
                  ? 'bg-console-phase-hover'
                  : ''
              }`}
            >
              <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${
                isActive ? 'bg-console-accent' : isDone ? 'bg-console-gold' : isFailed ? 'bg-console-accent' : 'bg-console-ink-deep'
              }`} />
              <span className={`truncate font-display text-sm ${
                isActive
                  ? 'text-console-ink italic'
                  : isDone
                    ? 'text-console-ink'
                    : isFailed
                      ? 'text-console-accent'
                      : 'text-console-ink-dim'
              }`}>{stage.label}</span>
              <span className={`ml-auto font-console-mono text-eyebrow shrink-0 uppercase tracking-wider ${
                isActive
                  ? 'text-console-accent'
                  : isDone
                    ? 'text-console-gold'
                    : isFailed
                      ? 'text-console-accent'
                      : 'text-console-ink-mute'
              }`}>
                {isActive ? 'Live' : isDone ? 'Done' : isFailed ? 'Fail' : 'Queue'}
              </span>
              {isActive && isPaused && (
                <span className="ml-1 text-console-accent shrink-0 font-console-mono text-eyebrow">[paused]</span>
              )}
            </li>
          )
        })}
      </ul>
      {failedShots.length > 0 && (
        <div className="mt-4 pt-3 border-t border-console-rule">
          <span className="text-xs font-console-mono text-console-accent">
            {failedShots.length} failed
          </span>
        </div>
      )}
    </aside>
  )
}
