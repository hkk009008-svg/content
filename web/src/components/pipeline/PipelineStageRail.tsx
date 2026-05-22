import type { PipelineStage, StageStatus } from '../../types/project'

/* Roman numerals up to XII — enough for any realistic pipeline length.
   Falls back to the 1-based index past XII (defensive only). */
const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']
const toRoman = (i: number): string => ROMAN[i] ?? String(i + 1)

const pad2 = (n: number) => n.toString().padStart(2, '0')

const STATUS_LABEL: Record<StageStatus, string> = {
  pending: 'Queued',
  running: 'Live',
  complete: 'Done',
  failed: 'Failed',
}

interface Props {
  stages: PipelineStage[]
  activeStage: string | null
}

export default function PipelineStageRail({ stages, activeStage }: Props) {
  const doneCount = stages.filter(s => s.status === 'complete').length

  return (
    <aside className="w-72 px-7 py-8 bg-editorial-ink overflow-y-auto">
      {/* Section label — matches the mockup's .section-label pattern */}
      <div
        className="flex justify-between items-center pb-3 mb-2 border-b border-editorial-rule
                   font-mono text-[10px] tracking-wide-eyebrow uppercase text-editorial-ivory-mute"
      >
        <span>Production Phases</span>
        <span className="text-editorial-ivory-soft tabular-nums">
          {pad2(doneCount)} / {pad2(stages.length)}
        </span>
      </div>

      <ol>
        {stages.map((stage, i) => {
          const isActive = activeStage === stage.id
          const isDone = stage.status === 'complete'
          const isFailed = stage.status === 'failed'

          /* Colors per state. The active row gets the curtain red,
             done rows the warm brass, failed rows the curtain (deeper). */
          const romanColor = isFailed
            ? 'text-editorial-curtain'
            : isActive
            ? 'text-editorial-curtain'
            : isDone
            ? 'text-editorial-ivory'
            : 'text-editorial-ivory-mute'

          const nameColor = isFailed
            ? 'text-editorial-curtain'
            : isActive
            ? 'text-editorial-ivory'
            : isDone
            ? 'text-editorial-ivory'
            : 'text-editorial-ivory-mute'

          const statusColor = isFailed
            ? 'text-editorial-curtain'
            : isActive
            ? 'text-editorial-curtain'
            : isDone
            ? 'text-editorial-brass'
            : 'text-editorial-ivory-mute'

          return (
            <li
              key={stage.id}
              className="grid grid-cols-[28px_1fr_auto] gap-3.5 items-baseline
                         py-4 border-b border-editorial-rule
                         relative group"
            >
              {/* Active-row pulsing dot — sits in the gutter to the left of Roman */}
              {isActive && (
                <span
                  className="absolute -left-4 top-1/2 -translate-y-1/2 w-1.5 h-1.5
                             rounded-full bg-editorial-curtain flicker"
                  aria-hidden
                />
              )}

              {/* Roman numeral — Fraunces with small-caps feature.
                  The mockup uses opsz 24 + WONK 1 for the active state. */}
              <span
                className={`font-display text-[17px] ${romanColor} tabular-nums`}
                style={{
                  fontVariationSettings: isActive
                    ? "'opsz' 24, 'WONK' 1, 'wght' 420"
                    : "'opsz' 24, 'WONK' 1, 'wght' 380",
                  fontFeatureSettings: '"smcp"',
                }}
              >
                {toRoman(i)}
              </span>

              {/* Stage name — italic when active, regular otherwise */}
              <span
                className={`font-display text-[19px] leading-tight ${nameColor}`}
                style={{
                  fontVariationSettings: isActive
                    ? "'opsz' 24, 'SOFT' 80, 'WONK' 1, 'wght' 420"
                    : "'opsz' 24, 'SOFT' 30, 'wght' 400",
                  fontStyle: isActive ? 'italic' : 'normal',
                  letterSpacing: '-0.005em',
                }}
              >
                {stage.label}
              </span>

              {/* Status word — mono, wide-tracked, uppercase */}
              <span
                className={`font-mono text-[9px] tracking-wide-eyebrow uppercase ${statusColor}`}
              >
                {STATUS_LABEL[stage.status] ?? stage.status}
              </span>
            </li>
          )
        })}
      </ol>
    </aside>
  )
}
