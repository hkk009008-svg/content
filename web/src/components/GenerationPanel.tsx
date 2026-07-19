import type { Project, ProgressEvent } from '../types/project'
import { stageTone } from '../lib/stageTone'

interface Props {
  project: Project
  events: ProgressEvent[]
  latest: ProgressEvent | null
  isGenerating: boolean
}

export default function GenerationPanel({ project, events, latest, isGenerating }: Props) {
  return (
    <div className="p-4">
      <h2 className="text-sm font-semibold text-mut uppercase tracking-wider mb-3">
        Generation {isGenerating && <span className="animate-pulse ml-1">LIVE</span>}
      </h2>

      {/* Progress Bar */}
      {latest && latest.percent >= 0 && (
        <div className="mb-3">
          <div className="flex justify-between text-eyebrow text-mut mb-1">
            <span>{latest.stage}</span>
            <span>{Math.round(latest.percent)}%</span>
          </div>
          <div
            className="w-full bg-app rounded-full h-1.5"
            role="progressbar"
            aria-valuenow={Math.round(latest.percent)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${latest.stage} progress`}
          >
            <div
              className="bg-acc rounded-full h-1.5 transition-all duration-500"
              style={{ width: `${Math.min(100, latest.percent)}%` }}
            />
          </div>
          <p className="text-eyebrow text-mut mt-1">
            {latest.detail}
            {latest.engine && (
              <span className="ml-2 font-mono text-tx">via {latest.engine}</span>
            )}
          </p>
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
          <p className="text-mut text-xs py-4 text-center">
            Configure your scenes, then click "Generate Film" to start.
          </p>
        )}
        {[...events].reverse().slice(0, 50).map((e, i) => (
          <div key={i} className="flex gap-2 text-eyebrow py-0.5">
            <span className={`font-mono w-16 shrink-0 ${stageTone(e.stage)}`}>
              {e.stage}
            </span>
            <span className="text-mut truncate">{e.detail}</span>
            {/* P1-3 (NF-3): the engine being tried — MOTION events carry
                percent=-1, so the progress block above is hidden during the
                exact wait this field exists for; the log line is the
                pipeline-mode surface. */}
            {e.engine && (
              <span className="font-mono text-tx shrink-0">via {e.engine}</span>
            )}
            {e.percent >= 0 && (
              <span className="text-mut ml-auto shrink-0">{Math.round(e.percent)}%</span>
            )}
          </div>
        ))}
      </div>

      {/* Pipeline Stats */}
      {!isGenerating && events.length > 0 && (
        <div className="mt-3 pt-3 border-t border-line">
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-lg font-bold text-tx">
                {events.filter(e => e.stage === 'VALIDATED').length}
              </div>
              <div className="text-eyebrow-sm text-mut">Identity Passes</div>
            </div>
            <div>
              <div className="text-lg font-bold text-warn">
                {events.filter(e => e.stage === 'RETRY' || e.stage === 'IDENTITY_FAIL').length}
              </div>
              <div className="text-eyebrow-sm text-mut">Retries</div>
            </div>
            <div>
              <div className="text-lg font-bold text-ok">
                {events.filter(e => e.stage === 'SCENE').length}
              </div>
              <div className="text-eyebrow-sm text-mut">Scenes Done</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
