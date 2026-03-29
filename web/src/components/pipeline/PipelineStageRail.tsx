import type { PipelineStage } from '../../types/project'

const STAGE_ICONS: Record<string, string> = {
  STYLE: '🎨',
  AUDIO: '🎵',
  DECOMPOSE: '✂️',
  DIRECTOR: '🎬',
  DIALOGUE: '🎙️',
  GENERATE: '🖼️',
  VIDEO: '📹',
  INTERP: '⚡',
  ASSEMBLY: '🎞️',
}

interface Props {
  stages: PipelineStage[]
  activeStage: string | null
}

export default function PipelineStageRail({ stages, activeStage }: Props) {
  return (
    <div className="w-16 border-r border-cinema-border flex flex-col items-center py-4 gap-1 bg-cinema-bg">
      {stages.map((stage, i) => {
        const isActive = activeStage === stage.id
        const dotColor =
          stage.status === 'complete' ? 'bg-cinema-success' :
          stage.status === 'running' ? 'bg-cinema-accent animate-pulse' :
          stage.status === 'failed' ? 'bg-cinema-danger' :
          'bg-cinema-muted/30'

        return (
          <div
            key={stage.id}
            className="flex flex-col items-center gap-0.5 py-1.5 group relative"
            title={stage.label}
          >
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-sm
              ${isActive ? 'bg-cinema-accent/20 ring-1 ring-cinema-accent' : 'bg-cinema-panel'}
            `}>
              {STAGE_ICONS[stage.id] || (i + 1)}
            </div>
            <div className={`w-2 h-2 rounded-full ${dotColor}`} />
            {/* Tooltip */}
            <div className="absolute left-14 top-1 hidden group-hover:block bg-cinema-panel border border-cinema-border
              px-2 py-1 rounded text-xs text-cinema-text whitespace-nowrap z-50 shadow-lg">
              {stage.label}
            </div>
          </div>
        )
      })}
    </div>
  )
}
