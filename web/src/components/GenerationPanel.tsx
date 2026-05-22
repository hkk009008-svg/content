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
    SCENE: 'text-editorial-brass',
    DECOMPOSE: 'text-cyan-400',
    DIALOGUE: 'text-pink-400',
    GENERATE: 'text-yellow-400',
    VIDEO: 'text-orange-400',
    VALIDATED: 'text-editorial-ready',
    IDENTITY_FAIL: 'text-editorial-curtain',
    RETRY: 'text-editorial-warn',
    ASSEMBLY: 'text-indigo-400',
    COMPLETE: 'text-editorial-ready',
    DONE: 'text-editorial-ready',
    ERROR: 'text-editorial-curtain',
    CANCELLED: 'text-editorial-ivory-mute',
    WARNING: 'text-editorial-warn',
  }

  return (
    <div className="p-4">
      <h2 className="text-sm font-semibold text-editorial-ivory-mute uppercase tracking-wider mb-3">
        Generation {isGenerating && <span className="animate-pulse ml-1">LIVE</span>}
      </h2>

      {/* Progress Bar */}
      {latest && latest.percent >= 0 && (
        <div className="mb-3">
          <div className="flex justify-between text-eyebrow text-editorial-ivory-mute mb-1">
            <span>{latest.stage}</span>
            <span>{Math.round(latest.percent)}%</span>
          </div>
          <div
            className="w-full bg-editorial-ink rounded-full h-1.5"
            role="progressbar"
            aria-valuenow={Math.round(latest.percent)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${latest.stage} progress`}
          >
            <div
              className="bg-editorial-brass rounded-full h-1.5 transition-all duration-500"
              style={{ width: `${Math.min(100, latest.percent)}%` }}
            />
          </div>
          <p className="text-eyebrow text-editorial-ivory-mute mt-1">{latest.detail}</p>
        </div>
      )}

      {/* Event Log — screen readers hear new events as they stream */}
      <div
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-label="Pipeline event log"
        className="max-h-64 overflow-y-auto space-y-0.5"
      >
        {events.length === 0 && !isGenerating && (
          <p className="text-editorial-ivory-mute text-xs py-4 text-center">
            Configure your scenes, then click "Generate Film" to start.
          </p>
        )}
        {[...events].reverse().slice(0, 50).map((e, i) => (
          <div key={i} className="flex gap-2 text-eyebrow py-0.5">
            <span className={`font-mono w-16 shrink-0 ${stageColors[e.stage] || 'text-editorial-ivory-mute'}`}>
              {e.stage}
            </span>
            <span className="text-editorial-ivory-mute truncate">{e.detail}</span>
            {e.percent >= 0 && (
              <span className="text-editorial-ivory-mute ml-auto shrink-0">{Math.round(e.percent)}%</span>
            )}
          </div>
        ))}
      </div>

      {/* Pipeline Stats */}
      {!isGenerating && events.length > 0 && (
        <div className="mt-3 pt-3 border-t border-editorial-rule">
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-bold text-editorial-ivory">
                {events.filter(e => e.stage === 'VALIDATED').length}
              </div>
              <div className="text-eyebrow-sm text-editorial-ivory-mute">Identity Passes</div>
            </div>
            <div>
              <div className="text-lg font-bold text-editorial-warn">
                {events.filter(e => e.stage === 'RETRY' || e.stage === 'IDENTITY_FAIL').length}
              </div>
              <div className="text-eyebrow-sm text-editorial-ivory-mute">Retries</div>
            </div>
            <div>
              <div className="text-lg font-bold text-editorial-ready">
                {events.filter(e => e.stage === 'SCENE').length}
              </div>
              <div className="text-eyebrow-sm text-editorial-ivory-mute">Scenes Done</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
