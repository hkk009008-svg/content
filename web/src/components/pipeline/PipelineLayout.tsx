import type { Project, ProgressEvent, ShotState, PipelineStage, DirectorReview } from '../../types/project'
import PipelineHeader from './PipelineHeader'
import PipelineStageRail from './PipelineStageRail'
import SceneExecutionCard from './SceneExecutionCard'
import DirectorReviewCard from './DirectorReviewCard'
import AssemblyGate from './AssemblyGate'
import ReviewStage from './ReviewStage'
import ScreeningStage from './ScreeningStage'
import GenerationPanel from '../GenerationPanel'
import Filmstrip from './Filmstrip'
import BudgetHaltBanner from '../BudgetHaltBanner'
import { ErrorState, LoadingState } from '../ui'

export interface PipelineError {
  message: string
  hint?: string
  onRetry?: () => void
}

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
  onApproveShotPlan: (shotId: string) => Promise<any>
  onRejectShotPlan: (shotId: string, reason?: string) => Promise<any>
  onGenerateKeyframe: (shotId: string, positive?: string, negative?: string) => Promise<any>
  onApproveKeyframe: (shotId: string, takeId: string) => Promise<any>
  onApprovePerformance: (shotId: string, takeId: string) => Promise<any>
  onGenerateMotion: (shotId: string) => Promise<any>
  onApproveFinal: (shotId: string, takeId: string) => Promise<any>
  onRegenerateShot: (shotId: string, positive?: string, negative?: string) => Promise<any>
  /** "Full restart" for a shot — clear every approval, regenerate the keyframe.
   *  Wired into ReviewStage's `onRegenerate` button. Distinct from onRegenerateShot
   *  (legacy "advance to next stage" semantics used by SceneExecutionCard). */
  onRestartShot: (shotId: string, positive?: string, negative?: string) => Promise<any>
  onCorrectShot: (shotId: string, action: string, params?: Record<string, any>, takeId?: string) => Promise<any>
  onDiagnoseShot: (shotId: string, takeId?: string, deep?: boolean) => Promise<any>
  onProceedToAssembly: () => Promise<any>
  /** Refresh the project from the server (rehydrate state). Used by
   *  ReviewStage's auto-approve rejection flow to clear the badge once
   *  the server has dropped the `<gate>_auto_approved` flag. */
  onRefreshProject: () => Promise<void> | void
  /** S17 + S18: directorial iteration. Optional — only passed when
   *  CINEMA_DIRECTORIAL_ITERATION is enabled. Forwarded to ReviewStage.
   *  S18 extends the signature with `targetStage` (KEYFRAME_REVIEW →
   *  'keyframe', PERFORMANCE_REVIEW → 'performance', REVIEW → 'motion')
   *  plus an optional structured `verb` + `params` for the verb DSL.
   *  Defaults preserve S17 freeform behaviour. */
  onIterate?: (
    shotId: string,
    takeId: string,
    prose: string,
    targetStage?: 'keyframe' | 'performance' | 'motion',
    verb?: string,
    params?: Record<string, unknown>,
  ) => Promise<any>
  /** S20 (cycle-9 Surface B): operator approves the screened cut.
   *  POSTs to /api/projects/<pid>/screening/approve. Only invoked when
   *  the SCREENING stage is active (i.e. CINEMA_SCREENING_STAGE was on
   *  at pipeline-start time). Forwarded into ScreeningStage. */
  onApproveFinalCut?: () => Promise<void>
  /** S21 (cycle-9 Surface B): operator triggers a full re-assembly of
   *  the cut after iterating shots during SCREENING. Forwarded into
   *  ScreeningStage. Caller (App.tsx) maps to ``reassembleProject(only_if_changed)``
   *  on the hook; returns the endpoint's JSON shape:
   *    { success, new_assembled_path, regenerated_shots, cost_estimate_seconds, skipped }
   *  (typed ``any`` here since the consuming component owns the shape). */
  onReassemble?: (onlyIfChanged: boolean) => Promise<any>
  /** Optional system-level error to render in the execution board. */
  pipelineError?: PipelineError | null
  /** Optional system-level "awaiting backend" placeholder. */
  pipelineLoadingLabel?: string | null
  /** P1-3: sticky BUDGET_EXCEEDED halt (owned by App.tsx so it survives
   *  mode switches; the gate fires mid-run while the operator is HERE). */
  budgetHalt?: ProgressEvent | null
  onDismissBudgetHalt?: () => void
}

/* ─── Helpers ─────────────────────────────────────────────────── */

const pad2 = (n: number) => n.toString().padStart(2, '0')

const formatRuntime = (seconds: number): string => {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${pad2(s)}`
}

/* ─── Vertical telemetry gauge ──────────────────────────────────
   One gauge = label · big serif value (with optional unit) · 2px
   underline fill bar. Tone (curtain / brass / ivory) is set by
   the caller via the `tone` prop. */
type GaugeTone = 'curtain' | 'brass' | 'ivory' | 'ready' | 'warn' | 'fail'

const TONE_FILL: Record<GaugeTone, string> = {
  curtain: 'bg-editorial-curtain',
  brass: 'bg-editorial-brass',
  ivory: 'bg-editorial-ivory',
  ready: 'bg-editorial-ready',
  warn: 'bg-editorial-warn',
  fail: 'bg-editorial-fail',
}

const TONE_TEXT: Record<GaugeTone, string> = {
  curtain: 'text-editorial-curtain',
  brass: 'text-editorial-brass',
  ivory: 'text-editorial-ivory',
  ready: 'text-editorial-ready',
  warn: 'text-editorial-warn',
  fail: 'text-editorial-fail',
}

function Gauge({
  label,
  value,
  unit,
  fillPercent,
  tone = 'ivory',
}: {
  label: string
  value: string
  unit?: string
  fillPercent: number
  tone?: GaugeTone
}) {
  const safePercent = Math.max(0, Math.min(100, fillPercent))
  return (
    <div className="mb-7">
      <div className="font-mono text-eyebrow-sm tracking-wide-eyebrow uppercase
                      text-editorial-ivory-mute mb-2">
        {label}
      </div>
      <div
        className={`font-display text-[42px] leading-none mb-2.5 tabular-nums ${TONE_TEXT[tone]}`}
        style={{ fontVariationSettings: "'opsz' 96, 'wght' 340, 'SOFT' 30" }}
      >
        {value}
        {unit && (
          <span className="text-[13px] text-editorial-ivory-mute align-top ml-1.5"
                style={{ fontVariationSettings: "'opsz' 14, 'wght' 400" }}>
            {unit}
          </span>
        )}
      </div>
      <div className="h-0.5 bg-editorial-rule relative overflow-hidden">
        <div
          className={`absolute inset-y-0 left-0 ${TONE_FILL[tone]} transition-all duration-700`}
          style={{ width: `${safePercent}%` }}
        />
      </div>
    </div>
  )
}

export default function PipelineLayout({
  project, events, latest, stages, activeStage,
  shotStates, directorReview, isGenerating, isPaused, failedShots,
  onBack, onCancel, onPause, onResume, onApproveShotPlan, onRejectShotPlan,
  onGenerateKeyframe, onApproveKeyframe, onApprovePerformance, onGenerateMotion, onApproveFinal,
  onRegenerateShot, onRestartShot, onCorrectShot, onDiagnoseShot, onProceedToAssembly,
  onRefreshProject, onIterate, onApproveFinalCut, onReassemble,
  pipelineError, pipelineLoadingLabel,
  budgetHalt, onDismissBudgetHalt,
}: Props) {
  const isComplete = latest?.stage === 'COMPLETE' || latest?.stage === 'DONE'

  /* ── Computed: editorial figures (counter, runtime, scenes) ───── */
  const totalShots = project.scenes.reduce(
    (sum, s) => sum + (s.shots?.length ?? s.num_shots ?? 0),
    0,
  )
  const completedShots = Array.from(shotStates.values()).filter(s =>
    s.status === 'complete' || s.status === 'post_processing' || s.status === 'image_review',
  ).length
  const inProgressOffset = isGenerating && !isComplete && completedShots < totalShots ? 1 : 0
  const currentShot = Math.min(totalShots, completedShots + inProgressOffset)
  const totalRuntime = project.scenes.reduce((sum, s) => sum + (s.duration_seconds || 0), 0)

  const eyebrowLabel = isComplete
    ? 'Final Cut'
    : isPaused
    ? 'Held'
    : isGenerating
    ? 'Now Filming'
    : 'Standing By'

  /* ── Quality summary (logic preserved from prior implementation) */
  const shotArray = Array.from(shotStates.values())
  const identityScores = shotArray.filter(s => s.identity_score != null).map(s => s.identity_score!)
  const avgIdentity =
    identityScores.length > 0
      ? identityScores.reduce((a, b) => a + b, 0) / identityScores.length
      : null

  const completionPercent = totalShots > 0 ? (completedShots / totalShots) * 100 : 0

  /* Identity tone — green/yellow/red based on average. */
  const identityTone: GaugeTone =
    avgIdentity == null
      ? 'ivory'
      : avgIdentity >= 0.7
      ? 'ready'
      : avgIdentity >= 0.55
      ? 'warn'
      : 'fail'

  const failedFillPercent =
    totalShots > 0 ? (failedShots.length / totalShots) * 100 : 0

  return (
    <div className="min-h-screen bg-editorial-ink text-editorial-ivory flex flex-col font-sans">
      {/* Top letterbox — animated slam-in, only while filming */}
      {isGenerating && (
        <div className="letterbox-bar top h-7 bg-black flex-none" aria-hidden />
      )}

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

      {budgetHalt && onDismissBudgetHalt && (
        <BudgetHaltBanner event={budgetHalt} onDismiss={onDismissBudgetHalt} />
      )}

      {/* ── Hero band — the editorial moment ────────────────────── */}
      <section className="px-12 pt-16 pb-12 border-b border-editorial-curtain relative">
        <div className="font-mono text-eyebrow tracking-wide-eyebrow uppercase text-editorial-curtain absolute top-6 left-12 z-10">
          {eyebrowLabel}
        </div>

        <div className="grid grid-cols-[auto_1fr] gap-12 items-end">
          <div
            className="font-display text-editorial-ivory leading-[0.78] tracking-tight-display ink-up"
            style={{
              fontSize: 'clamp(140px, 19vw, 320px)',
              fontVariationSettings: '"opsz" 144, "WONK" 1, "wght" 320, "SOFT" 0',
            }}
          >
            {pad2(currentShot)}
            <span
              className="text-[0.16em] text-editorial-ivory-mute align-super -ml-1"
              style={{ fontVariationSettings: '"opsz" 24, "WONK" 0, "wght" 350' }}
            >
              /{pad2(totalShots)}
            </span>
          </div>

          <div className="pb-6">
            <h1
              className="font-display italic text-editorial-ivory ink-up mb-5"
              style={{
                fontSize: 'clamp(36px, 5vw, 76px)',
                fontVariationSettings: '"opsz" 96, "SOFT" 60, "WONK" 1, "wght" 380',
                lineHeight: 0.95,
                letterSpacing: '-0.02em',
              }}
            >
              {project.name}
            </h1>
            <div className="font-mono text-eyebrow-lg tracking-wide-eyebrow uppercase text-editorial-ivory-mute flex flex-wrap items-center gap-x-5 gap-y-2">
              <span>{formatRuntime(totalRuntime)} Runtime</span>
              <span className="text-editorial-rule-bright">·</span>
              <span>{project.scenes.length} Scenes</span>
              <span className="text-editorial-rule-bright">·</span>
              <span>{totalShots} Shots</span>
              <span className="text-editorial-rule-bright">·</span>
              <span>9:16 Vertical</span>
              {isGenerating && !isPaused && (
                <>
                  <span className="text-editorial-rule-bright">·</span>
                  <span className="text-editorial-curtain inline-flex items-center gap-2 flicker">
                    <span className="w-1.5 h-1.5 rounded-full bg-editorial-curtain" />
                    On Air
                  </span>
                </>
              )}
              {isPaused && (
                <>
                  <span className="text-editorial-rule-bright">·</span>
                  <span className="text-editorial-brass inline-flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-editorial-brass" />
                    Held
                  </span>
                </>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* ── Filmstrip — sprocket-hole reel of all shots ────────── */}
      <Filmstrip project={project} shotStates={shotStates} />

      {/* ── Main grid — stage rail · execution board · telemetry rail ─ */}
      <div className="flex flex-1 overflow-hidden">
        {/* Stage rail (left) */}
        <div className="border-r border-editorial-rule">
          <PipelineStageRail stages={stages} activeStage={activeStage} />
        </div>

        {/* Execution board (center) */}
        <div className="flex-1 overflow-y-auto px-8 py-6 bg-editorial-ink">
          {pipelineError ? (
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
          ) : (['PLAN_REVIEW', 'KEYFRAME_REVIEW', 'PERFORMANCE_REVIEW', 'REVIEW'].includes(activeStage || '')) ||
          (isPaused && ['PLAN_REVIEW', 'KEYFRAME_REVIEW', 'PERFORMANCE_REVIEW', 'REVIEW'].includes(activeStage || '')) ? (
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
                <div className="text-center py-24">
                  <p
                    className="font-display italic text-editorial-ivory-mute mb-3"
                    style={{
                      fontSize: 'clamp(28px, 3vw, 44px)',
                      fontVariationSettings: '"opsz" 48, "SOFT" 80, "WONK" 1',
                    }}
                  >
                    No scenes defined
                  </p>
                  <p className="font-mono text-eyebrow-lg uppercase tracking-wide-eyebrow text-editorial-ivory-faint">
                    Return to setup to compose the picture
                  </p>
                </div>
              )}

              {isComplete && <AssemblyGate project={project} />}
            </>
          )}
        </div>

        {/* Right rail — telemetry gauges + event log */}
        <aside className="w-80 border-l border-editorial-rule overflow-y-auto bg-editorial-ink-soft/30 flex flex-col">
          <div className="px-8 py-7">
            <div
              className="flex justify-between items-center pb-3 mb-5 border-b border-editorial-rule
                         font-mono text-eyebrow tracking-wide-eyebrow uppercase text-editorial-ivory-mute"
            >
              <span>Telemetry</span>
              <span className="text-editorial-ivory-soft">
                {isGenerating && !isPaused ? 'Live' : isPaused ? 'Held' : 'Standby'}
              </span>
            </div>

            <Gauge
              label="Identity Pass Rate"
              value={avgIdentity == null ? '—' : Math.round(avgIdentity * 100).toString()}
              unit={avgIdentity == null ? undefined : `% · ${identityScores.length} shot${identityScores.length === 1 ? '' : 's'}`}
              fillPercent={avgIdentity == null ? 0 : avgIdentity * 100}
              tone={identityTone}
            />

            <Gauge
              label="Shots Complete"
              value={`${pad2(completedShots)} / ${pad2(totalShots)}`}
              fillPercent={completionPercent}
              tone="brass"
            />

            <Gauge
              label="Failed Takes"
              value={pad2(failedShots.length)}
              unit={failedShots.length === 0 ? 'none — clean run' : 'skipped'}
              fillPercent={failedFillPercent}
              tone={failedShots.length === 0 ? 'ivory' : 'fail'}
            />
          </div>

          {/* Event log — kept underneath, separated by a hairline */}
          <div className="border-t border-editorial-rule flex-1 overflow-y-auto">
            <GenerationPanel
              project={project}
              events={events}
              latest={latest}
              isGenerating={isGenerating}
            />
          </div>
        </aside>
      </div>

      {/* Bottom letterbox — closes the frame */}
      {isGenerating && (
        <div className="letterbox-bar bottom h-7 bg-black flex-none" aria-hidden />
      )}
    </div>
  )
}
