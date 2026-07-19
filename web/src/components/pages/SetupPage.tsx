import type { Project, AppConfig, ProgressEvent } from '../../types/project'
import CharacterPanel from '../CharacterPanel'
import LocationPanel from '../LocationPanel'
import ObjectPanel from '../ObjectPanel'
import ScenePanel from '../ScenePanel'
import SettingsPanel from '../SettingsPanel'
import GenerationPanel from '../GenerationPanel'
import PreviewPanel from '../PreviewPanel'

/**
 * SetupPage (stub) — mounts the six existing workshop panels unchanged so
 * every functional flow (project mutate + SSE) keeps working while later
 * tasks flesh out the redesigned Setup surface. This is the current 3-col
 * workshop grid lifted out of `EditorialShell`; the editorial chrome around
 * it (hero, cue sheet, action bar) now lives in `AppShell`.
 *
 * Panel prop contracts are matched EXACTLY to the existing components:
 *   Character / Location / Scene / Settings → {project, config, onRefresh}
 *   Object → {project, onRefresh}          (ObjectPanel takes no `config`)
 *   Generation → {project, events, latest, isGenerating}
 *   Preview → {project}
 */

interface Props {
  project: Project
  config: AppConfig | null
  events: ProgressEvent[]
  latest: ProgressEvent | null
  isGenerating: boolean
  onRefreshProject: () => Promise<void> | void
}

export default function SetupPage({
  project,
  config,
  events,
  latest,
  isGenerating,
  onRefreshProject,
}: Props) {
  return (
    <div
      data-page="setup"
      className="grid grid-cols-12 h-full min-h-0 bg-app text-tx"
    >
      {/* Left: cast + locations + objects */}
      <div className="col-span-3 border-r border-line overflow-y-auto bg-gutter">
        <CharacterPanel project={project} config={config} onRefresh={onRefreshProject} />
        <div className="border-t border-line" />
        <LocationPanel project={project} config={config} onRefresh={onRefreshProject} />
        <div className="border-t border-line" />
        <ObjectPanel project={project} onRefresh={onRefreshProject} />
      </div>

      {/* Center: scenes (editing) */}
      <div className="col-span-6 overflow-y-auto bg-app">
        <ScenePanel project={project} config={config} onRefresh={onRefreshProject} />
      </div>

      {/* Right: settings + generation + preview */}
      <div className="col-span-3 border-l border-line overflow-y-auto bg-gutter">
        <SettingsPanel project={project} config={config} onRefresh={onRefreshProject} />
        <div className="border-t border-line" />
        <GenerationPanel
          project={project}
          events={events}
          latest={latest}
          isGenerating={isGenerating}
        />
        <div className="border-t border-line" />
        <PreviewPanel project={project} />
      </div>
    </div>
  )
}
