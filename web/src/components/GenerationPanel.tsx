import type { Project, ProgressEvent } from '../types/project'

interface Props {
  project: Project
  events: ProgressEvent[]
  latest: ProgressEvent | null
  isGenerating: boolean
}

export default function GenerationPanel({ project, events, latest, isGenerating }: Props) {
  const stageColors: Record<string, string> = {
    STYLE: 'text-purple-400',
    AUDIO: 'text-blue-400',
    SCENE: 'text-cinema-accent',
    DECOMPOSE: 'text-cyan-400',
    DIALOGUE: 'text-pink-400',
    GENERATE: 'text-yellow-400',
    VIDEO: 'text-orange-400',
    VALIDATED: 'text-cinema-success',
    IDENTITY_FAIL: 'text-cinema-danger',
    RETRY: 'text-cinema-warning',
    ASSEMBLY: 'text-indigo-400',
    COMPLETE: 'text-cinema-success',
    DONE: 'text-cinema-success',
    ERROR: 'text-cinema-danger',
    CANCELLED: 'text-cinema-muted',
    WARNING: 'text-cinema-warning',
  }

  return (
    <div className="p-4">
      <h2 className="text-sm font-semibold text-cinema-muted uppercase tracking-wider mb-3">
        Generation {isGenerating && <span className="animate-pulse ml-1">LIVE</span>}
      </h2>

      {/* Progress Bar */}
      {latest && latest.percent >= 0 && (
        <div className="mb-3">
          <div className="flex justify-between text-[10px] text-cinema-muted mb-1">
            <span>{latest.stage}</span>
            <span>{Math.round(latest.percent)}%</span>
          </div>
          <div className="w-full bg-cinema-bg rounded-full h-1.5">
            <div
              className="bg-cinema-accent rounded-full h-1.5 transition-all duration-500"
              style={{ width: `${Math.min(100, latest.percent)}%` }}
            />
          </div>
          <p className="text-[10px] text-cinema-muted mt-1">{latest.detail}</p>
        </div>
      )}

      {/* Event Log */}
      <div className="max-h-64 overflow-y-auto space-y-0.5">
        {events.length === 0 && !isGenerating && (
          <p className="text-cinema-muted text-xs py-4 text-center">
            Configure your scenes, then click "Generate Film" to start.
          </p>
        )}
        {[...events].reverse().slice(0, 50).map((e, i) => (
          <div key={i} className="flex gap-2 text-[10px] py-0.5">
            <span className={`font-mono w-16 shrink-0 ${stageColors[e.stage] || 'text-cinema-muted'}`}>
              {e.stage}
            </span>
            <span className="text-cinema-muted truncate">{e.detail}</span>
            {e.percent >= 0 && (
              <span className="text-cinema-muted ml-auto shrink-0">{Math.round(e.percent)}%</span>
            )}
          </div>
        ))}
      </div>

      {/* Pipeline Stats */}
      {!isGenerating && events.length > 0 && (
        <div className="mt-3 pt-3 border-t border-cinema-border">
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-bold text-cinema-text">
                {events.filter(e => e.stage === 'VALIDATED').length}
              </div>
              <div className="text-[9px] text-cinema-muted">Identity Passes</div>
            </div>
            <div>
              <div className="text-lg font-bold text-cinema-warning">
                {events.filter(e => e.stage === 'RETRY' || e.stage === 'IDENTITY_FAIL').length}
              </div>
              <div className="text-[9px] text-cinema-muted">Retries</div>
            </div>
            <div>
              <div className="text-lg font-bold text-cinema-success">
                {events.filter(e => e.stage === 'SCENE').length}
              </div>
              <div className="text-[9px] text-cinema-muted">Scenes Done</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
