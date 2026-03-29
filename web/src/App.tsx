import { useState, useEffect, useCallback } from 'react'
import type { Project, AppConfig, ProgressEvent } from './types/project'
import { usePipelineState } from './hooks/usePipelineState'
import CharacterPanel from './components/CharacterPanel'
import LocationPanel from './components/LocationPanel'
import ScenePanel from './components/ScenePanel'
import SettingsPanel from './components/SettingsPanel'
import GenerationPanel from './components/GenerationPanel'
import PreviewPanel from './components/PreviewPanel'
import ProjectSelector from './components/ProjectSelector'
import PipelineLayout from './components/pipeline/PipelineLayout'

const API = '/api'

export default function App() {
  const [project, setProject] = useState<Project | null>(null)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [generating, setGenerating] = useState(false)
  const [mode, setMode] = useState<'setup' | 'pipeline'>('setup')

  const {
    events, latest, isStreaming, start: startSSE, stop: stopSSE,
    stages, activeStage, shotStates, directorReview, processEvent,
    isPaused, failedShots, pause: pausePipeline, resume: resumePipeline,
    regenerateShot, correctShot, diagnoseShot, proceedToAssembly,
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

  // Process SSE events through pipeline state router
  useEffect(() => {
    if (latest) processEvent(latest)
  }, [latest, processEvent])

  // Watch for generation completion
  useEffect(() => {
    if (latest?.stage === 'DONE' || latest?.stage === 'ERROR' || latest?.stage === 'COMPLETE') {
      setGenerating(false)
    }
  }, [latest])

  if (!project) {
    return <ProjectSelector onSelect={loadProject} />
  }

  // --- PIPELINE MODE ---
  if (mode === 'pipeline' && project) {
    return (
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
        onBack={handleBackToSetup}
        onCancel={handleCancel}
        onPause={pausePipeline}
        onResume={resumePipeline}
        onRegenerateShot={regenerateShot}
        onCorrectShot={correctShot}
        onDiagnoseShot={diagnoseShot}
        onProceedToAssembly={proceedToAssembly}
      />
    )
  }

  // --- SETUP MODE ---
  return (
    <div className="min-h-screen bg-cinema-bg">
      {/* Header — glass with subtle gradient */}
      <header className="bg-gradient-header border-b border-cinema-border-subtle px-6 py-3 flex items-center justify-between shadow-panel">
        <div className="flex items-center gap-4">
          <button
            onClick={() => setProject(null)}
            className="text-cinema-muted hover:text-cinema-gold text-sm transition-colors"
          >
            &larr; Projects
          </button>
          <div className="w-px h-5 bg-cinema-border" />
          <h1 className="text-lg font-semibold text-cinema-text tracking-tight">{project.name}</h1>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-cinema-muted bg-cinema-panel-elevated px-2.5 py-1 rounded-full border border-cinema-border-subtle">
              {project.scenes.length} scenes
            </span>
            <span className="text-[11px] text-cinema-muted bg-cinema-panel-elevated px-2.5 py-1 rounded-full border border-cinema-border-subtle">
              {project.characters.length} characters
            </span>
            <span className="text-[11px] text-cinema-muted bg-cinema-panel-elevated px-2.5 py-1 rounded-full border border-cinema-border-subtle">
              {project.locations.length} locations
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {!generating ? (
            <button
              onClick={handleGenerate}
              disabled={project.scenes.length === 0}
              className="bg-gradient-accent hover:shadow-glow-accent disabled:opacity-30 px-6 py-2 rounded-lg text-white font-semibold text-sm shadow-panel"
            >
              Generate Film
            </button>
          ) : (
            <button
              onClick={handleCancel}
              className="bg-cinema-danger-dim hover:bg-cinema-danger px-5 py-2 rounded-lg text-white font-medium text-sm"
            >
              Cancel
            </button>
          )}
          {project.scenes.length > 0 && !generating && (
            <a
              href={`${API}/projects/${project.id}/export`}
              className="border border-cinema-border hover:border-cinema-gold hover:text-cinema-gold px-4 py-2 rounded-lg text-cinema-text-secondary text-sm transition-colors"
            >
              Download MP4
            </a>
          )}
        </div>
      </header>

      {/* Dashboard Grid — All panels visible */}
      <div className="grid grid-cols-12 gap-0 h-[calc(100vh-57px)]">

        {/* Left Column: Characters + Locations (stacked) */}
        <div className="col-span-3 border-r border-cinema-border-subtle overflow-y-auto bg-cinema-bg-deep">
          <CharacterPanel
            project={project}
            config={config}
            onRefresh={refreshProject}
          />
          <div className="border-t border-cinema-border-subtle" />
          <LocationPanel
            project={project}
            config={config}
            onRefresh={refreshProject}
          />
        </div>

        {/* Center: Scene Timeline + Editor */}
        <div className="col-span-6 overflow-y-auto bg-cinema-bg">
          <ScenePanel
            project={project}
            config={config}
            onRefresh={refreshProject}
          />
        </div>

        {/* Right Column: Settings + Generation + Preview (stacked) */}
        <div className="col-span-3 border-l border-cinema-border-subtle overflow-y-auto bg-cinema-bg-deep">
          <SettingsPanel
            project={project}
            config={config}
            onRefresh={refreshProject}
          />
          <div className="border-t border-cinema-border-subtle" />
          <GenerationPanel
            project={project}
            events={events}
            latest={latest}
            isGenerating={generating || isStreaming}
          />
          <div className="border-t border-cinema-border-subtle" />
          <PreviewPanel project={project} />
        </div>
      </div>
    </div>
  )
}
