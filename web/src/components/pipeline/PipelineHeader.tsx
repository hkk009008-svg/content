import { useState, useEffect } from 'react'
import type { PipelineStage } from '../../types/project'

interface Props {
  projectName: string
  stages: PipelineStage[]
  activeStage: string | null
  isPaused: boolean
  failedShots: string[]
  onBack: () => void
  onCancel: () => void
  onPause: () => void
  onResume: () => void
}

const pad2 = (n: number) => n.toString().padStart(2, '0')

export default function PipelineHeader({
  projectName, stages, activeStage, isPaused, failedShots,
  onBack, onCancel, onPause, onResume,
}: Props) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (isPaused) return
    const t = setInterval(() => setElapsed(e => e + 1), 1000)
    return () => clearInterval(t)
  }, [isPaused])

  const mins = Math.floor(elapsed / 60)
  const secs = elapsed % 60
  const currentLabel =
    isPaused
      ? 'Held'
      : stages.find(s => s.id === activeStage)?.label ?? 'Standing by'

  return (
    <div
      className="px-10 py-4 flex items-center justify-between gap-6
                 border-b border-editorial-rule bg-editorial-ink"
    >
      {/* Left — back link + project marker */}
      <div className="flex items-center gap-8 min-w-0">
        <button
          onClick={onBack}
          className="font-mono text-eyebrow-lg text-editorial-ivory-mute tracking-wide-eyebrow
                     uppercase hover:text-editorial-brass link-editorial whitespace-nowrap"
        >
          ← The Archive
        </button>

        <div className="flex items-baseline gap-3 min-w-0">
          <span
            className="font-display text-editorial-ivory text-base truncate"
            style={{ fontVariationSettings: "'opsz' 24, 'wght' 450, 'SOFT' 30" }}
          >
            {projectName}
          </span>
          <span className="font-mono text-eyebrow tracking-wide-eyebrow uppercase
                           text-editorial-ivory-mute whitespace-nowrap">
            {isPaused ? 'Held' : 'On Air'}
          </span>
          {failedShots.length > 0 && (
            <span
              className="font-mono text-eyebrow tracking-wide-eyebrow uppercase
                         text-editorial-curtain whitespace-nowrap"
              title={`${failedShots.length} shot(s) failed and were skipped`}
            >
              · {failedShots.length} Skipped
            </span>
          )}
        </div>
      </div>

      {/* Right — current stage, timer, action verbs */}
      <div className="flex items-center gap-6 flex-shrink-0">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-eyebrow tracking-wide-eyebrow uppercase
                           text-editorial-ivory-mute">
            Now
          </span>
          <span
            className={`font-display text-base ${
              isPaused ? 'text-editorial-brass' : 'text-editorial-ivory'
            }`}
            style={{
              fontVariationSettings: isPaused
                ? "'opsz' 24, 'SOFT' 80, 'WONK' 1, 'wght' 420"
                : "'opsz' 24, 'wght' 420, 'SOFT' 30",
              fontStyle: isPaused ? 'italic' : 'normal',
            }}
          >
            {currentLabel}
          </span>
        </div>

        <span className="font-mono text-eyebrow-lg text-editorial-ivory-soft tabular-nums tracking-wide-eyebrow">
          {pad2(mins)}:{pad2(secs)}
        </span>

        {/* Hairline buttons in editorial vocabulary —
            flat squared rectangles, mono eyebrow text, no fills. */}
        {isPaused ? (
          <button
            onClick={onResume}
            className="px-5 py-2.5 font-mono text-eyebrow tracking-wide-eyebrow uppercase
                       border border-editorial-brass text-editorial-brass
                       hover:bg-editorial-brass hover:text-editorial-ink transition-colors"
          >
            Resume Filming
          </button>
        ) : (
          <button
            onClick={onPause}
            className="px-5 py-2.5 font-mono text-eyebrow tracking-wide-eyebrow uppercase
                       border border-editorial-rule-bright text-editorial-ivory-soft
                       hover:border-editorial-brass hover:text-editorial-brass transition-colors"
          >
            Hold the Print
          </button>
        )}

        <button
          onClick={onCancel}
          className="px-5 py-2.5 font-mono text-eyebrow tracking-wide-eyebrow uppercase
                     border border-editorial-curtain text-editorial-curtain
                     hover:bg-editorial-curtain hover:text-editorial-ivory transition-colors"
        >
          Strike the Print
        </button>
      </div>
    </div>
  )
}
