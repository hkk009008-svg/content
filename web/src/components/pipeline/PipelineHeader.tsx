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
  const completedCount = stages.filter(s => s.status === 'complete').length
  const currentLabel = isPaused ? 'Paused' : (stages.find(s => s.id === activeStage)?.label || 'Initializing...')

  return (
    <div className="border-b border-cinema-border px-6 py-3 flex items-center justify-between bg-cinema-bg">
      <div className="flex items-center gap-4">
        <button onClick={onBack} className="text-cinema-muted hover:text-cinema-text text-sm">
          &larr; Back to Setup
        </button>
        <h1 className="text-lg font-semibold text-cinema-text">{projectName}</h1>
        <span className={`text-xs px-2 py-1 rounded font-mono ${
          isPaused ? 'text-cinema-warning bg-cinema-warning/10' : 'text-cinema-accent bg-cinema-accent/10'
        }`}>
          {isPaused ? 'PAUSED' : 'PIPELINE MODE'}
        </span>
        {failedShots.length > 0 && (
          <span className="text-xs text-cinema-danger bg-cinema-danger/10 px-2 py-1 rounded font-mono">
            {failedShots.length} SKIPPED
          </span>
        )}
      </div>

      <div className="flex items-center gap-4">
        {/* Mini stage progress */}
        <div className="flex items-center gap-1">
          {stages.map(s => (
            <div
              key={s.id}
              className={`w-3 h-3 rounded-full transition-colors ${
                s.status === 'complete' ? 'bg-cinema-success' :
                s.status === 'running' ? (isPaused ? 'bg-cinema-warning' : 'bg-cinema-accent animate-pulse') :
                'bg-cinema-muted/20'
              }`}
              title={s.label}
            />
          ))}
        </div>

        <span className="text-sm text-cinema-text">{currentLabel}</span>

        <span className="text-xs text-cinema-muted font-mono">
          {completedCount}/{stages.length} &middot; {mins}:{secs.toString().padStart(2, '0')}
        </span>

        {/* Pause / Resume button */}
        {isPaused ? (
          <button
            onClick={onResume}
            className="bg-cinema-success/80 hover:bg-cinema-success px-4 py-1.5 rounded text-white text-sm"
          >
            Resume
          </button>
        ) : (
          <button
            onClick={onPause}
            className="bg-cinema-warning/80 hover:bg-cinema-warning px-4 py-1.5 rounded text-black text-sm"
          >
            Pause
          </button>
        )}

        <button
          onClick={onCancel}
          className="bg-cinema-danger/80 hover:bg-cinema-danger px-4 py-1.5 rounded text-white text-sm"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
