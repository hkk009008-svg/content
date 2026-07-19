import { useMemo } from 'react'
import type { Project, ProgressEvent, ShotState, PipelineStage, DirectorReview } from '../../types/project'
import PipelineStageRail from '../pipeline/PipelineStageRail'
import ReviewStage from '../pipeline/ReviewStage'
import ScreeningStage from '../pipeline/ScreeningStage'
import SceneExecutionCard from '../pipeline/SceneExecutionCard'
import DirectorReviewCard from '../pipeline/DirectorReviewCard'
import AssemblyGate from '../pipeline/AssemblyGate'
import Monitor from '../console/Monitor'
import Telemetry from '../console/Telemetry'
import Notes from '../console/Notes'
import Filmstrip from '../shared/Filmstrip'
import { ErrorState, LoadingState, MICRO_LABEL } from '../ui'

/**
 * RunPage — the merged live-run surface. It folds the old `PipelineLayout`
 * (stage rail + execution/review/screening routing + gates) and the old
 * `DirectorsConsole` (Monitor / Telemetry / Notes monitoring surfaces) into a
 * single page, and renders the one canonical `shared/Filmstrip`.
 *
 * REGRESSION CONTRACT — the `activeStage` routing below is reproduced
 * byte-for-byte from `PipelineLayout` (the review/keyframe/performance/final
 * approval gates + the SCREENING gate depend on exactly which component renders
 * for which stage). Every `on*` callback is threaded through unchanged. The
 * surrounding chrome (header, stage rail, filmstrip, monitor, telemetry, notes)
 * is additive and does not touch the gate flow.
 *
 * The prop contract below was originally `ComponentProps<typeof PipelineLayout>`
 * (the old file this page replaced); Task 13 inlined it as an explicit local
 * type so `pipeline/PipelineLayout.tsx` — now dead (no JSX mount anywhere) —
 * could be deleted. Field-for-field identical to the old shape.
 * `AppShell` derives its own pipeline-prop `Pick<>` from `ComponentProps<typeof
 * RunPage>` (this component), not from PipelineLayout. `budgetHalt` is owned by
 * `AppShell` (single banner) and is intentionally not consumed here.
 *
 * `activeShotId` and `notesBuffer` are NOT threaded to this page, so they are
 * derived from `events` exactly as `usePipelineState` derives them (most-recent
 * non-failure `shot_id`; newest-first rolling tail of the last 20 events) — no
 * second SSE subscription is opened.
 *
 * Indigo design tokens throughout (bg-app, bg-head, border-line,
 * text-tx/-mut/-dim). The reused legacy components now use these same tokens —
 * the editorial- and console- palettes were retired.
 */

const REVIEW_STAGES = ['PLAN_REVIEW', 'KEYFRAME_REVIEW', 'PERFORMANCE_REVIEW', 'REVIEW']

/** Mirrors the old `pipeline/PipelineLayout` `Props` shape (minus `budgetHalt`
 *  / `onDismissBudgetHalt`, which RunPage never consumed — see file doc above).
 *  `AppShell.tsx` derives its `Pick<>` from `ComponentProps<typeof RunPage>`. */
interface PipelineErrorLike {
  message: string
  hint?: string
  onRetry?: () => void
}

export interface Props {
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
  onApproveShotPlan: (shotId: string) => Promise<any>
  onRejectShotPlan: (shotId: string, reason?: string) => Promise<any>
  onGenerateKeyframe: (shotId: string, positive?: string, negative?: string) => Promise<any>
  onApproveKeyframe: (shotId: string, takeId: string) => Promise<any>
  onApprovePerformance: (shotId: string, takeId: string) => Promise<any>
  onGenerateMotion: (shotId: string) => Promise<any>
  onApproveFinal: (shotId: string, takeId: string) => Promise<any>
  onRegenerateShot: (shotId: string, positive?: string, negative?: string) => Promise<any>
  onRestartShot: (shotId: string, positive?: string, negative?: string) => Promise<any>
  onCorrectShot: (shotId: string, action: string, params?: Record<string, any>, takeId?: string) => Promise<any>
  onDiagnoseShot: (shotId: string, takeId?: string, deep?: boolean) => Promise<any>
  onProceedToAssembly: () => Promise<any>
  onRefreshProject: () => Promise<void> | void
  onIterate?: (
    shotId: string,
    takeId: string,
    prose: string,
    targetStage?: 'keyframe' | 'performance' | 'motion',
    verb?: string,
    params?: Record<string, unknown>,
  ) => Promise<any>
  onApproveFinalCut?: () => Promise<void>
  onReassemble?: (onlyIfChanged: boolean) => Promise<any>
  pipelineError?: PipelineErrorLike | null
  pipelineLoadingLabel?: string | null
}

export default function RunPage({
  project, events, latest, stages, activeStage,
  shotStates, directorReview, isGenerating, isPaused, failedShots,
  onBack, onCancel, onPause, onResume, onApproveShotPlan, onRejectShotPlan,
  onGenerateKeyframe, onApproveKeyframe, onApprovePerformance, onGenerateMotion, onApproveFinal,
  onRegenerateShot, onRestartShot, onCorrectShot, onDiagnoseShot, onProceedToAssembly,
  onRefreshProject, onIterate, onApproveFinalCut, onReassemble,
  pipelineError, pipelineLoadingLabel,
}: Props) {
  const projectId = project.id
  const isComplete = latest?.stage === 'COMPLETE' || latest?.stage === 'DONE'

  /* Derived (RunPage is not passed these) — mirrors usePipelineState. */
  const activeShotId = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const e = events[i]
      if (e.shot_id && e.stage !== 'SHOT_FAILED') return e.shot_id
    }
    return null
  }, [events])

  const notesBuffer = useMemo(() => events.slice(-20).reverse(), [events])

  /* Header runstat. */
  const totalShots = project.scenes.reduce(
    (sum, s) => sum + (s.shots?.length ?? s.num_shots ?? 0),
    0,
  )
  const completedShots = Array.from(shotStates.values()).filter(
    (s) => s.status === 'complete' || s.status === 'post_processing' || s.status === 'image_review',
  ).length
  const statusWord = isPaused ? 'held' : isGenerating ? 'running' : 'idle'

  /* ── Center content — routed on activeStage EXACTLY as PipelineLayout ──
     Do not reorder or alter these branches: the approval/screening gates
     depend on which component renders for which stage. */
  const centerContent = pipelineError ? (
    <ErrorState
      message={pipelineError.message}
      hint={pipelineError.hint}
      onRetry={pipelineError.onRetry}
      onDismiss={onCancel}
      dismissLabel="Back to setup"
    />
  ) : pipelineLoadingLabel ? (
    <div className="py-24 flex justify-center">
      <LoadingState label={pipelineLoadingLabel} size="lg" />
    </div>
  ) : activeStage === 'SCREENING' && onApproveFinalCut ? (
    <ScreeningStage
      project={project}
      onApproveFinal={onApproveFinalCut}
      onIterate={onIterate}
      onRefreshProject={onRefreshProject}
      onReassemble={onReassemble}
    />
  ) : (REVIEW_STAGES.includes(activeStage || '')) ||
    (isPaused && REVIEW_STAGES.includes(activeStage || '')) ? (
    <ReviewStage
      project={project}
      activeStage={activeStage}
      shotStates={shotStates}
      onApprovePlan={onApproveShotPlan}
      onRejectPlan={onRejectShotPlan}
      onGenerateKeyframe={onGenerateKeyframe}
      onApproveKeyframe={onApproveKeyframe}
      onApprovePerformance={onApprovePerformance}
      onGenerateMotion={onGenerateMotion}
      onApproveFinal={onApproveFinal}
      onCorrect={onCorrectShot}
      onDiagnose={(shotId, takeId, deep) => onDiagnoseShot(shotId, takeId, deep)}
      onRegenerate={onRestartShot}
      onProceedToAssembly={onProceedToAssembly}
      onRefreshProject={onRefreshProject}
      onIterate={onIterate}
    />
  ) : (
    <>
      <DirectorReviewCard review={directorReview} />

      {project.scenes.length > 0 ? (
        project.scenes.map((scene) => (
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
        <div className="py-24 text-center">
          <p className="font-sans text-2xl text-mut">No scenes defined</p>
          <p className={`${MICRO_LABEL} mt-2`}>Return to setup to compose the picture</p>
        </div>
      )}

      {isComplete && <AssemblyGate project={project} />}
    </>
  )

  return (
    <div data-page="run" className="flex h-full min-h-0 flex-col bg-app text-tx font-sans">
      {/* ── Header strip — runstat + run controls ─────────────────── */}
      <div className="flex flex-none items-center justify-between border-b border-line bg-head px-4 py-2">
        <div className="flex items-center gap-3">
          <span className={MICRO_LABEL}>Run · {statusWord}</span>
          <span className="font-mono text-[11px] tabular-nums text-dim">
            {completedShots}/{totalShots} shots
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[11px] uppercase tracking-wide">
          {isPaused ? (
            <button onClick={onResume} className="text-pri hover:text-tx">Resume</button>
          ) : isGenerating ? (
            <button onClick={onPause} className="text-mut hover:text-tx">Pause</button>
          ) : null}
          <button onClick={onCancel} className="text-mut hover:text-fail">Cancel</button>
          <button onClick={onBack} className="text-mut hover:text-tx">Back</button>
        </div>
      </div>

      {/* ── Canonical filmstrip — the single merged reel ──────────── */}
      <div className="flex-none">
        <Filmstrip
          project={project}
          shotStates={shotStates}
          projectId={projectId}
          activeShotId={activeShotId}
        />
      </div>

      {/* ── Main row — stage rail · monitor+routed board · telemetry/notes ── */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Left — production phases (all 14 stages incl. SCREENING) */}
        <div className="flex-none overflow-y-auto border-r border-line">
          <PipelineStageRail stages={stages} activeStage={activeStage} />
        </div>

        {/* Center — live monitor above the routed execution/review board */}
        <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">
          <Monitor
            project={project}
            activeShotId={activeShotId}
            shotStates={shotStates}
            projectId={projectId}
            directorReview={directorReview}
          />
          <div className="px-6 py-6">{centerContent}</div>
        </div>

        {/* Right — telemetry + director notes */}
        <aside className="flex w-80 flex-none flex-col overflow-y-auto border-l border-line">
          <Telemetry
            project={project}
            shotStates={shotStates}
            failedShots={failedShots}
            isStreaming={isGenerating}
            projectId={projectId}
          />
          <Notes notesBuffer={notesBuffer} />
        </aside>
      </div>
    </div>
  )
}
