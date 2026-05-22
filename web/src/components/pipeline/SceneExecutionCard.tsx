import { useState } from 'react'
import type { Scene, Shot, ShotState } from '../../types/project'
import ShotRow from './ShotRow'

interface Props {
  scene: Scene
  shotStates: Map<string, Partial<ShotState>>
  isActive: boolean
  projectId: string
  onRegenerateShot?: (shotId: string) => Promise<any>
}

export default function SceneExecutionCard({ scene, shotStates, isActive, projectId, onRegenerateShot }: Props) {
  const [expanded, setExpanded] = useState(true)

  const shots = scene.shots || []
  const completedShots = shots.filter(s => {
    const state = shotStates.get(s.id)
    return state?.status === 'complete'
  }).length

  const hasErrors = shots.some(s => shotStates.get(s.id)?.status === 'failed')

  return (
    <div className={`border border-editorial-rule rounded-lg overflow-hidden mb-3
      ${isActive ? 'ring-1 ring-editorial-brass/50' : ''}
    `}>
      {/* Scene header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 bg-editorial-ink-soft hover:bg-editorial-ink-soft/80 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-editorial-ivory font-medium text-sm">
            {scene.title || `Scene ${scene.order + 1}`}
          </span>
          <span className="text-eyebrow text-editorial-ivory-mute bg-editorial-ink px-2 py-0.5 rounded">
            {shots.length} shots &middot; {scene.duration_seconds}s
          </span>
          {isActive && (
            <span className="text-eyebrow text-editorial-brass bg-editorial-brass/10 px-2 py-0.5 rounded animate-pulse">
              ACTIVE
            </span>
          )}
          {hasErrors && (
            <span className="text-eyebrow text-editorial-curtain bg-editorial-curtain/10 px-2 py-0.5 rounded">
              ERRORS
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-editorial-ivory-mute">
            {completedShots}/{shots.length}
          </span>
          {/* Progress bar */}
          <div className="w-20 h-1.5 bg-editorial-ink rounded-full overflow-hidden">
            <div
              className="h-full bg-editorial-ready rounded-full transition-all"
              style={{ width: shots.length > 0 ? `${(completedShots / shots.length) * 100}%` : '0%' }}
            />
          </div>
          <span className="text-editorial-ivory-mute text-xs">{expanded ? '▲' : '▼'}</span>
        </div>
      </button>

      {/* Shots */}
      {expanded && (
        <div className="bg-editorial-ink">
          {shots.length > 0 ? (
            shots.map((shot, i) => (
              <ShotRow
                key={shot.id}
                shot={shot}
                shotState={shotStates.get(shot.id)}
                shotIndex={i}
                sceneId={scene.id}
                projectId={projectId}
                onRegenerate={onRegenerateShot}
              />
            ))
          ) : (
            <div className="px-4 py-6 text-center text-editorial-ivory-mute text-sm">
              Shots will appear here during decomposition...
            </div>
          )}
        </div>
      )}
    </div>
  )
}
