import { useEffect, useRef, useState, type ComponentProps } from 'react'
import type { Project, AppConfig, ProgressEvent } from '../types/project'
import { usePage, type Page } from '../context/PageContext'
import { Badge, StatusDot, ErrorBoundary } from './ui'
import BudgetHaltBanner from './BudgetHaltBanner'
import PostRunSummary from './console/PostRunSummary'
import SetupPage from './pages/SetupPage'
import EditPage from './pages/EditPage'
import RunPage from './pages/RunPage'
import CapabilityPage from './pages/CapabilityPage'

/**
 * AppShell — the single persistent shell that replaced the old four-`mode`
 * router in `App.tsx`. One top bar + one bottom page-bar wrap a `switch(page)`
 * center region; navigation is `usePage().setPage`, so a page switch never
 * unmounts the shell.
 *
 * Prop contract = the old `EditorialShell` set (so `App.tsx` still passes one
 * object) PLUS every prop the old `PipelineLayout` consumed (threaded through
 * to the Run page). `budgetHalt` is still owned by `App.tsx`; the shell renders
 * its banner in the always-mounted top region so the sticky halt survives page
 * switches — this replaces the old dual-mount (EditorialShell + PipelineLayout).
 *
 * Task 13: `pipeline/PipelineLayout.tsx` is deleted (dead — no JSX mount
 * anywhere), so the pipeline-prop `Pick<>` below is derived from
 * `ComponentProps<typeof RunPage>` instead; `RunPage.tsx` carries the
 * field-for-field-identical `Props` type PipelineLayout used to own.
 */

type PipelineProps = ComponentProps<typeof RunPage>

interface AppShellProps
  extends Pick<
    PipelineProps,
    // ── Run-page pipeline state ──
    | 'stages'
    | 'activeStage'
    | 'shotStates'
    | 'directorReview'
    | 'isPaused'
    | 'failedShots'
    // ── Slice 11c: server-derived action authority + checkpoint summary ──
    | 'allowedActions'
    | 'checkpoint'
    | 'queue'
    // ── Run-page callbacks (wrapped in withRefresh up in App.tsx) ──
    | 'onBack'
    | 'onAbandonQueueJob'
    | 'onPause'
    | 'onResume'
    | 'onResumeFromCheckpoint'
    | 'onApproveShotPlan'
    | 'onRejectShotPlan'
    | 'onGenerateKeyframe'
    | 'onApproveKeyframe'
    | 'onApprovePerformance'
    | 'onGenerateMotion'
    | 'onApproveFinal'
    | 'onRegenerateShot'
    | 'onRestartShot'
    | 'onCorrectShot'
    | 'onDiagnoseShot'
    | 'onProceedToAssembly'
    | 'onIterate'
    | 'onApproveFinalCut'
    | 'onReassemble'
    | 'pipelineError'
    | 'pipelineLoadingLabel'
  > {
  // ── EditorialShell-parity props ──
  project: Project
  config: AppConfig | null
  events: ProgressEvent[]
  latest: ProgressEvent | null
  /** SSE transport connectivity only -- NEVER job truth (Slice 11b). Kept
   *  in the prop contract for parity with App.tsx's call site; `isGenerating`
   *  below deliberately derives from `generating` alone. */
  isStreaming: boolean
  generating: boolean
  onBackToProjects: () => void
  onGenerate: () => void
  onCancel: () => void
  onRefreshProject: () => Promise<void> | void
  onOpenConsole?: () => void
  onOpenCapability?: () => void
  apiBase: string
  /** P1-3: sticky BUDGET_EXCEEDED halt — owned by App.tsx; rendered in the
   *  always-mounted top region so it survives page switches. */
  budgetHalt?: ProgressEvent | null
  onDismissBudgetHalt?: () => void
}

/* ─── Chrome constants ────────────────────────────────────────── */

const TABS: { id: Page; glyph: string; label: string }[] = [
  { id: 'setup', glyph: '◧', label: 'Setup' },
  { id: 'edit', glyph: '✂', label: 'Edit' },
  { id: 'run', glyph: '▷', label: 'Run' },
  { id: 'capability', glyph: '▤', label: 'Capability' },
]

// Rough per-shot cost used only for the top-bar estimate chrome (display, not
// a gate). Order-of-magnitude of a Veo-class 8s clip; later tasks refine.
const EST_PER_SHOT_USD = 3

/* ─── Shell ───────────────────────────────────────────────────── */

export default function AppShell({
  project,
  config,
  events,
  latest,
  isStreaming,
  generating,
  onBackToProjects,
  onGenerate,
  onCancel,
  onRefreshProject,
  onOpenConsole: _onOpenConsole,
  onOpenCapability: _onOpenCapability,
  apiBase,
  budgetHalt,
  onDismissBudgetHalt,
  // ── pipeline (Run page) ──
  stages,
  activeStage,
  shotStates,
  directorReview,
  isPaused,
  failedShots,
  allowedActions,
  checkpoint,
  queue,
  onBack,
  onAbandonQueueJob,
  onPause,
  onResume,
  onResumeFromCheckpoint,
  onApproveShotPlan,
  onRejectShotPlan,
  onGenerateKeyframe,
  onApproveKeyframe,
  onApprovePerformance,
  onGenerateMotion,
  onApproveFinal,
  onRegenerateShot,
  onRestartShot,
  onCorrectShot,
  onDiagnoseShot,
  onProceedToAssembly,
  onIterate,
  onApproveFinalCut,
  onReassemble,
  pipelineError,
  pipelineLoadingLabel,
}: AppShellProps) {
  const { page, setPage } = usePage()

  // Slice 11b: `isGenerating` must derive ONLY from backend truth --
  // `generating` is App.tsx's `running || starting` (slice 8a's
  // server-confirmed `running`, OR'd with this session's own in-flight
  // /generate POST). `isStreaming` is SSE TRANSPORT connectivity, never
  // job truth (mirrors `_pipeline_action_authority`'s own docstring on
  // the backend: "a client can disconnect from the SSE stream while
  // generation keeps running, and vice versa"). A momentary reconnect
  // must never flip a truthful "running" to "idle", and a live-but-idle
  // stream must never manufacture a "running" the backend hasn't
  // confirmed -- both were possible while this was `generating ||
  // isStreaming`. `isStreaming` remains an accepted prop (App.tsx's call
  // site still passes it; other pages may still want raw connectivity
  // later) but is deliberately NOT read here anymore.
  const isGenerating = generating
  const reelNumber = project.id.slice(0, 4).toUpperCase()

  /* ── Shot tally (bottom-left runstat) ─────────────────────────── */
  const totalShots = project.scenes.reduce(
    (sum, s) => sum + (s.shots?.length ?? s.num_shots ?? 0),
    0,
  )
  const completedShots = Array.from(shotStates.values()).filter(
    (s) => s.status === 'complete' || s.status === 'post_processing' || s.status === 'image_review',
  ).length

  const statusWord = isPaused ? 'held' : isGenerating ? 'running' : 'idle'
  const dotStatus = isPaused ? 'warn' : isGenerating ? 'run' : 'idle'
  const estCost = totalShots * EST_PER_SHOT_USD

  /* ── PostRunSummary auto-open-on-DONE dedup (ported from EditorialShell) ─
     Opens the summary when the pipeline reaches DONE. The dedup key includes
     a monotonic run counter that bumps on each transition OUT of DONE, so a
     re-broadcast of the same DONE event within one run is blocked, but a
     later run with an identical (stage, percent, detail) tuple still opens. */
  const [showPostRunSummary, setShowPostRunSummary] = useState(false)
  const lastDoneEventRef = useRef<string | null>(null)
  const runCounterRef = useRef(0)
  const lastStageRef = useRef<string | null>(null)

  useEffect(() => {
    if (!latest) return
    if (lastStageRef.current === 'DONE' && latest.stage !== 'DONE') {
      runCounterRef.current += 1
    }
    lastStageRef.current = latest.stage ?? null

    if (latest.stage === 'DONE') {
      const eventKey = `${runCounterRef.current}::${latest.stage}::${latest.percent}::${latest.detail}`
      if (lastDoneEventRef.current !== eventKey) {
        lastDoneEventRef.current = eventKey
        setShowPostRunSummary(true)
      }
    }
  }, [latest])

  /* ── Center: page switch ──────────────────────────────────────── */
  const renderPage = () => {
    switch (page) {
      case 'setup':
        return (
          <SetupPage
            project={project}
            config={config}
            events={events}
            latest={latest}
            isGenerating={isGenerating}
            onRefreshProject={onRefreshProject}
          />
        )
      case 'edit':
        return (
          <EditPage
            project={project}
            config={config}
            apiBase={apiBase}
            onRefreshProject={onRefreshProject}
            shotStates={shotStates}
          />
        )
      case 'run':
        return (
          <RunPage
            project={project}
            events={events}
            latest={latest}
            stages={stages}
            activeStage={activeStage}
            shotStates={shotStates}
            directorReview={directorReview}
            isGenerating={isGenerating}
            isPaused={isPaused}
            failedShots={failedShots}
            allowedActions={allowedActions}
            checkpoint={checkpoint}
            queue={queue}
            onBack={onBack}
            onCancel={onCancel}
            onAbandonQueueJob={onAbandonQueueJob}
            onPause={onPause}
            onResume={onResume}
            onResumeFromCheckpoint={onResumeFromCheckpoint}
            onGenerate={onGenerate}
            onApproveShotPlan={onApproveShotPlan}
            onRejectShotPlan={onRejectShotPlan}
            onGenerateKeyframe={onGenerateKeyframe}
            onApproveKeyframe={onApproveKeyframe}
            onApprovePerformance={onApprovePerformance}
            onGenerateMotion={onGenerateMotion}
            onApproveFinal={onApproveFinal}
            onRegenerateShot={onRegenerateShot}
            onRestartShot={onRestartShot}
            onCorrectShot={onCorrectShot}
            onDiagnoseShot={onDiagnoseShot}
            onProceedToAssembly={onProceedToAssembly}
            onRefreshProject={onRefreshProject}
            onIterate={onIterate}
            onApproveFinalCut={onApproveFinalCut}
            onReassemble={onReassemble}
            pipelineError={pipelineError}
            pipelineLoadingLabel={pipelineLoadingLabel}
          />
        )
      case 'capability':
        return <CapabilityPage project={project} />
    }
  }

  return (
    <div className="flex h-screen min-h-0 flex-col bg-app text-tx font-sans">
      {/* ── Top bar (38px) ─────────────────────────────────────── */}
      <header className="flex h-[38px] flex-none items-center gap-4 border-b border-line bg-head px-4">
        <button
          onClick={onBackToProjects}
          className="font-mono text-[11px] uppercase tracking-wide text-mut hover:text-tx"
          title="Back to projects"
        >
          ‹ Projects
        </button>
        <div className="flex items-center gap-2 min-w-0">
          <span className="truncate font-sans text-sm text-tx">
            {project.name || 'Untitled film'}
          </span>
          <span className="font-mono text-[10px] uppercase tracking-wide text-dim">
            Reel {reelNumber}
          </span>
        </div>

        <div className="flex-1" />

        {/* Cost estimate — display chrome only, not a budget gate. */}
        <span className="font-mono text-[10px] uppercase tracking-wide text-mut" title="Rough estimate — not a budget gate">
          est ~${estCost}
        </span>
        {/* Credential pills — provider/tier chrome derived from settings.
           Full per-credential wiring is a later task. */}
        <Badge variant="cloud">{project.global_settings?.aspect_ratio || '16:9'}</Badge>

        {/* Re-open PostRunSummary (parity with EditorialShell footer link). */}
        {lastDoneEventRef.current && !showPostRunSummary && (
          <button
            onClick={() => setShowPostRunSummary(true)}
            className="font-mono text-[10px] uppercase tracking-wide text-pri hover:text-tx"
            title="Re-open the auto-approve summary"
          >
            Summary
          </button>
        )}

        <button
          onClick={() => setPage('setup')}
          className="text-mut hover:text-tx"
          title="Settings (Setup)"
          aria-label="Settings"
        >
          <span aria-hidden>⚙</span>
        </button>
      </header>

      {/* ── Sticky budget-halt banner (App-owned; survives page switches) ── */}
      {budgetHalt && onDismissBudgetHalt && (
        <div className="flex-none">
          <BudgetHaltBanner event={budgetHalt} onDismiss={onDismissBudgetHalt} />
        </div>
      )}

      {/* ── Center: active page ────────────────────────────────── */}
      <main className="flex-1 min-h-0 overflow-hidden">
        <ErrorBoundary>{renderPage()}</ErrorBoundary>
      </main>

      {/* ── Legend row (pinned above the page-bar) ─────────────── */}
      <div className="flex flex-none items-center gap-3 border-t border-line bg-gutter px-4 py-1">
        <Badge variant="cloud">Cloud</Badge>
        <Badge variant="pod">Pod requires the pod</Badge>
        <Badge variant="pri">Primary</Badge>
      </div>

      {/* ── Bottom page-bar (52px) ─────────────────────────────── */}
      <footer className="flex h-[52px] flex-none items-center justify-between border-t border-line bg-head px-4">
        {/* Left: runstat */}
        <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wide text-mut">
          <StatusDot status={dotStatus} />
          <span>
            {statusWord} · {completedShots}/{totalShots} shots
          </span>
        </div>

        {/* Center: page tabs */}
        <nav className="flex items-center gap-1" aria-label="Pages">
          {TABS.map((tab) => {
            const active = page === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setPage(tab.id)}
                aria-current={active ? 'page' : undefined}
                className={[
                  'flex items-center gap-1.5 rounded px-3 py-1.5 font-mono text-[11px] uppercase tracking-wide transition-colors',
                  active ? 'bg-acc-dim text-white' : 'text-mut hover:text-tx',
                ].join(' ')}
              >
                <span aria-hidden>{tab.glyph}</span>
                {tab.label}
              </button>
            )
          })}
        </nav>

        {/* Right: generate */}
        <button
          onClick={onGenerate}
          disabled={project.scenes.length === 0 || !allowedActions.includes('start')}
          aria-label={queue?.state === 'queued' ? 'Generation queued' : queue?.state === 'running' ? 'Generation running' : 'Generate'}
          className="flex items-center gap-1.5 rounded bg-acc px-4 py-1.5 font-mono text-[11px] uppercase tracking-wide text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          <span aria-hidden>▶</span>
          {queue?.state === 'queued' ? 'Queued' : queue?.state === 'running' ? 'Running' : 'Generate'}
        </button>
      </footer>

      {/* PostRunSummary modal — triggered by the DONE SSE event. */}
      <PostRunSummary
        project={project}
        isOpen={showPostRunSummary}
        onClose={() => setShowPostRunSummary(false)}
        onRejectSuccess={onRefreshProject}
        apiBase={apiBase}
      />
    </div>
  )
}
