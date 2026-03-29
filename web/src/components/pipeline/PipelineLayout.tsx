import type { Project, ProgressEvent, ShotState, PipelineStage, DirectorReview } from '../../types/project'
import PipelineHeader from './PipelineHeader'
import PipelineStageRail from './PipelineStageRail'
import SceneExecutionCard from './SceneExecutionCard'
import DirectorReviewCard from './DirectorReviewCard'
import AssemblyGate from './AssemblyGate'
import ReviewStage from './ReviewStage'
import GenerationPanel from '../GenerationPanel'

interface Props {
  project: Project
  events: ProgressEvent[]
  latest: ProgressEvent | null
  stages: PipelineStage[]
  activeStage: string | null
  shotStates: Map<string, Partial<ShotState>>
  directorReview: DirectorReview | null
  isGenerating: boolean
  isPaused: boolean
  failedShots: string[]
  onBack: () => void
  onCancel: () => void
  onPause: () => void
  onResume: () => void
  onRegenerateShot: (shotId: string, positive?: string, negative?: string) => Promise<any>
  onCorrectShot: (shotId: string, action: string, params?: Record<string, any>) => Promise<any>
  onDiagnoseShot: (shotId: string) => Promise<any>
  onProceedToAssembly: () => void
}

export default function PipelineLayout({
  project, events, latest, stages, activeStage,
  shotStates, directorReview, isGenerating, isPaused, failedShots,
  onBack, onCancel, onPause, onResume, onRegenerateShot,
  onCorrectShot, onDiagnoseShot, onProceedToAssembly,
}: Props) {
  const isComplete = latest?.stage === 'COMPLETE' || latest?.stage === 'DONE'

  // Compute quality summary from shot states
  const shotArray = Array.from(shotStates.values())
  const identityScores = shotArray.filter(s => s.identity_score != null).map(s => s.identity_score!)
  const avgIdentity = identityScores.length > 0 ? identityScores.reduce((a, b) => a + b, 0) / identityScores.length : null

  return (
    <div className="min-h-screen bg-cinema-bg flex flex-col">
      <PipelineHeader
        projectName={project.name}
        stages={stages}
        activeStage={activeStage}
        isPaused={isPaused}
        failedShots={failedShots}
        onBack={onBack}
        onCancel={onCancel}
        onPause={onPause}
        onResume={onResume}
      />

      {/* Quality summary bar */}
      {identityScores.length > 0 && (
        <div className="border-b border-cinema-border bg-cinema-panel/50 px-6 py-2 flex items-center gap-6">
          <span className="text-xs text-cinema-muted uppercase tracking-wider">Quality</span>
          <div className="flex items-center gap-2">
            <span className="text-xs text-cinema-text">Avg Identity:</span>
            <span className={`text-xs font-mono font-bold ${
              avgIdentity! >= 0.70 ? 'text-cinema-success' :
              avgIdentity! >= 0.55 ? 'text-cinema-warning' : 'text-cinema-danger'
            }`}>
              {Math.round(avgIdentity! * 100)}%
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-cinema-text">Shots:</span>
            <span className="text-xs font-mono text-cinema-success">{shotArray.filter(s => s.status === 'image_review' || s.status === 'complete' || s.status === 'post_processing').length} done</span>
            {failedShots.length > 0 && (
              <span className="text-xs font-mono text-cinema-danger">{failedShots.length} failed</span>
            )}
          </div>
          {/* Identity distribution mini-bars */}
          <div className="flex items-center gap-0.5 ml-auto">
            {identityScores.map((score, i) => (
              <div
                key={i}
                className={`w-1.5 rounded-sm ${
                  score >= 0.70 ? 'bg-cinema-success' :
                  score >= 0.55 ? 'bg-cinema-warning' : 'bg-cinema-danger'
                }`}
                style={{ height: `${Math.max(4, score * 20)}px` }}
                title={`Shot ${i + 1}: ${Math.round(score * 100)}%`}
              />
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Stage Rail */}
        <PipelineStageRail stages={stages} activeStage={activeStage} />

        {/* Execution Board */}
        <div className="flex-1 overflow-y-auto p-4">
          {activeStage === 'REVIEW' || isPaused && activeStage === 'REVIEW' ? (
            /* Director's Cut Review Stage */
            <ReviewStage
              project={project}
              shotStates={shotStates}
              onCorrect={onCorrectShot}
              onDiagnose={onDiagnoseShot}
              onRegenerate={onRegenerateShot}
              onProceedToAssembly={onProceedToAssembly}
            />
          ) : (
            <>
              {/* Director Review */}
              <DirectorReviewCard review={directorReview} />

              {/* Scene Cards */}
              {project.scenes.length > 0 ? (
                project.scenes.map(scene => (
                  <SceneExecutionCard
                    key={scene.id}
                    scene={scene}
                    shotStates={shotStates}
                    isActive={true}
                    projectId={project.id}
                    onRegenerateShot={onRegenerateShot}
                  />
                ))
              ) : (
                <div className="text-center py-20 text-cinema-muted">
                  <p className="text-lg">No scenes defined</p>
                  <p className="text-sm mt-2">Go back to setup and add scenes first</p>
                </div>
              )}

              {/* Assembly Gate — shown on completion */}
              {isComplete && <AssemblyGate project={project} />}
            </>
          )}
        </div>

        {/* Right: Event Log */}
        <div className="w-72 border-l border-cinema-border overflow-y-auto">
          <GenerationPanel
            project={project}
            events={events}
            latest={latest}
            isGenerating={isGenerating}
          />
        </div>
      </div>
    </div>
  )
}
