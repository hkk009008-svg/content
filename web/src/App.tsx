import { useState, useEffect, useCallback } from 'react'
import type { Project, AppConfig } from './types/project'
import { usePipelineState } from './hooks/usePipelineState'
import { ErrorBoundary } from './components/ui'
import ProjectSelector from './components/ProjectSelector'
import PipelineLayout from './components/pipeline/PipelineLayout'
import EditorialShell from './components/EditorialShell'
import DirectorsConsole from './components/DirectorsConsole'
import CapabilityConsole from './components/console/CapabilityConsole'

const API = '/api'

export default function App() {
  const [project, setProject] = useState<Project | null>(null)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [generating, setGenerating] = useState(false)
  // 'console' is the new Director's Console route — design/directors-console.html
  // brought into the running app as a stub shell. Future slices flesh out the regions.
  const [mode, setMode] = useState<'setup' | 'pipeline' | 'console' | 'capability'>('setup')

  const {
    events, latest, isStreaming, start: startSSE, stop: stopSSE,
    stages, activeStage, shotStates, directorReview, processEvent,
    isPaused, failedShots, pause: pausePipeline, resume: resumePipeline,
    approveShotPlan, rejectShotPlan, generateKeyframe, approveKeyframe, approvePerformance, generateMotion, approveFinal,
    regenerateShot, restartShot, correctShot, diagnoseShot, proceedToAssembly, iterateTake,
    approveScreening, reassembleProject,
  } = usePipelineState(project?.id ?? null)

  // Load config on mount
  useEffect(() => {
    fetch(`${API}/config`).then(r => r.json()).then(setConfig).catch(() => {})
  }, [])

  const loadProject = useCallback(async (id: string) => {
    const res = await fetch(`${API}/projects/${id}`)
    if (res.ok) setProject(await res.json())
  }, [])

  const refreshProject = useCallback(async () => {
    if (project) await loadProject(project.id)
  }, [project, loadProject])

  const handleGenerate = async () => {
    if (!project) return
    setGenerating(true)
    setMode('pipeline')  // Switch to pipeline view
    await fetch(`${API}/projects/${project.id}/generate`, { method: 'POST' })
    startSSE()
  }

  const handleCancel = async () => {
    if (!project) return
    await fetch(`${API}/projects/${project.id}/cancel`, { method: 'POST' })
    stopSSE()
    setGenerating(false)
  }

  const handleBackToSetup = () => {
    setMode('setup')
  }

  const withRefresh = useCallback(async (action: () => Promise<any>) => {
    const result = await action()
    await refreshProject()
    return result
  }, [refreshProject])

  // Process SSE events through pipeline state router
  useEffect(() => {
    if (latest) processEvent(latest)
  }, [latest, processEvent])

  useEffect(() => {
    if (!latest || !project) return
    const refreshStages = new Set([
      'DECOMPOSE',
      'PLAN_REVIEW',
      'KEYFRAME_READY',
      'KEYFRAME_REVIEW',
      'MOTION_READY',
      'POSTPROCESS_READY',
      'REVIEW',
      'SCENE_PREVIEW',
      'COMPLETE',
    ])
    if (refreshStages.has(latest.stage)) {
      refreshProject()
    }
  }, [latest, project, refreshProject])

  // Watch for generation completion
  useEffect(() => {
    if (latest?.stage === 'DONE' || latest?.stage === 'ERROR' || latest?.stage === 'COMPLETE') {
      setGenerating(false)
    }
  }, [latest])

  if (!project) {
    return <ProjectSelector onSelect={loadProject} />
  }

  // --- DIRECTOR'S CONSOLE ---
  // New route from design/directors-console.html. Stub shell — see component
  // for region-level TODOs. Toggled via the masthead button in EditorialShell.
  if (mode === 'console' && project) {
    return <ErrorBoundary><DirectorsConsole project={project} onBack={() => setMode('setup')} /></ErrorBoundary>
  }

  // --- CAPABILITY DASHBOARD ---
  // Part 4: scorecard view. Toggled via the "Capability →" masthead button.
  if (mode === 'capability' && project) {
    return <ErrorBoundary><CapabilityConsole project={project} onBack={() => setMode('setup')} /></ErrorBoundary>
  }

  // --- PIPELINE MODE ---
  if (mode === 'pipeline' && project) {
    const pipelineError =
      latest?.stage === 'ERROR'
        ? {
            message: latest.failure_reason || latest.detail || 'The pipeline reported an error.',
            hint: 'The director has stopped the run. You can restart from setup, or retry to resume.',
            onRetry: handleGenerate,
          }
        : null

    const pipelineLoadingLabel =
      generating && !isStreaming && events.length === 0
        ? 'Calling the projection room'
        : null

    return (
      <ErrorBoundary>
        <PipelineLayout
          project={project}
          events={events}
          latest={latest}
          stages={stages}
          activeStage={activeStage}
          shotStates={shotStates}
          directorReview={directorReview}
          isGenerating={generating || isStreaming}
          isPaused={isPaused}
          failedShots={failedShots}
          pipelineError={pipelineError}
          pipelineLoadingLabel={pipelineLoadingLabel}
          onBack={handleBackToSetup}
          onCancel={handleCancel}
          onPause={pausePipeline}
          onResume={resumePipeline}
          onApproveShotPlan={(shotId) => withRefresh(() => approveShotPlan(shotId))}
          onRejectShotPlan={(shotId, reason) => withRefresh(() => rejectShotPlan(shotId, reason))}
          onGenerateKeyframe={(shotId, positive, negative) => withRefresh(() => generateKeyframe(shotId, positive, negative))}
          onApproveKeyframe={(shotId, takeId) => withRefresh(() => approveKeyframe(shotId, takeId))}
          onApprovePerformance={(shotId, takeId) => withRefresh(() => approvePerformance(shotId, takeId))}
          onGenerateMotion={(shotId) => withRefresh(() => generateMotion(shotId))}
          onApproveFinal={(shotId, takeId) => withRefresh(() => approveFinal(shotId, takeId))}
          onRegenerateShot={(shotId, positive, negative) => withRefresh(() => regenerateShot(shotId, positive, negative))}
          onRestartShot={(shotId, positive, negative) => withRefresh(() => restartShot(shotId, positive, negative))}
          onCorrectShot={(shotId, action, params, takeId) => withRefresh(() => correctShot(shotId, action, params, takeId))}
          onDiagnoseShot={(shotId, takeId, deep) => diagnoseShot(shotId, takeId, deep)}
          onProceedToAssembly={() => withRefresh(() => proceedToAssembly())}
          onRefreshProject={refreshProject}
          onIterate={(shotId, takeId, prose, targetStage, verb, params) =>
            withRefresh(() => iterateTake(shotId, takeId, prose, targetStage, verb, params))
          }
          onApproveFinalCut={async () => {
            await withRefresh(() => approveScreening())
          }}
          onReassemble={(onlyIfChanged) => reassembleProject(onlyIfChanged)}
        />
      </ErrorBoundary>
    )
  }

  // --- SETUP MODE ---
  // Render the editorial shell. It owns the chrome (hero, figures, cue
  // sheet, action bar) and embeds the existing functional panels in its
  // workshop section so SSE wiring + project-mutate flows are unchanged.
  return (
    <ErrorBoundary>
      <EditorialShell
        project={project}
        config={config}
        events={events}
        latest={latest}
        isStreaming={isStreaming}
        generating={generating}
        onBackToProjects={() => setProject(null)}
        onGenerate={handleGenerate}
        onCancel={handleCancel}
        onRefreshProject={refreshProject}
        onOpenConsole={() => setMode('console')}
        onOpenCapability={() => setMode('capability')}
        apiBase={API}
      />
    </ErrorBoundary>
  )
}
