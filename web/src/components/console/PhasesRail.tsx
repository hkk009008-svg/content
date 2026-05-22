import type { PipelineStage } from '../../types/project'

export interface PhasesRailProps {
  stages: PipelineStage[]
  activeStage: string | null
  isPaused: boolean
  failedShots: string[]
}

export default function PhasesRail({ stages, activeStage, isPaused, failedShots }: PhasesRailProps) {
  return (
    <aside className="col-span-2 border-r border-editorial-rule px-4 py-6 bg-editorial-ink-soft/30 flex flex-col">
      <h2 className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute mb-3">
        Phases
      </h2>
      <ul className="space-y-1.5 text-xs flex-1">
        {stages.map((stage) => {
          const isActive = stage.id === activeStage
          return (
            <li
              key={stage.id}
              className={`flex items-center gap-2 ${
                isActive
                  ? 'text-editorial-brass font-semibold'
                  : stage.status === 'complete'
                    ? 'text-editorial-ready'
                    : stage.status === 'failed'
                      ? 'text-editorial-curtain'
                      : 'text-editorial-ivory-mute'
              }`}
            >
              <span className="inline-block w-2 h-2 rounded-full bg-current opacity-60 shrink-0" />
              <span className="truncate">{stage.label}</span>
              {isActive && isPaused && (
                <span className="ml-auto text-editorial-curtain shrink-0">[paused]</span>
              )}
            </li>
          )
        })}
      </ul>
      {failedShots.length > 0 && (
        <div className="mt-4 pt-3 border-t border-editorial-rule">
          <span className="text-xs font-mono text-editorial-curtain">
            {failedShots.length} failed
          </span>
        </div>
      )}
    </aside>
  )
}
