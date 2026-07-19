import type { Project, AppConfig, ProgressEvent } from '../../types/project'
import ProjectTree from '../setup/ProjectTree'
import SceneCueSheet from '../setup/SceneCueSheet'
import SettingsPanel from '../SettingsPanel'

/**
 * SetupPage — 3-column Resolve-style layout: `ProjectTree | SceneCueSheet |
 * SettingsInspector`. Replaces the flat 3-col-grid stub (which mounted the
 * six workshop panels unchanged) now that the left column has its own tree
 * shell and the center has a real scenes cue sheet.
 *
 * The right column is an interim mount of the existing `SettingsPanel` —
 * `SettingsInspector` (the reconciled Video/Image/Identity/Voice/Budget
 * inspector) arrives in Task 8 and will replace this column wholesale.
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
    <div data-page="setup" className="flex h-full min-h-0 bg-app text-tx">
      <ProjectTree
        project={project}
        config={config}
        events={events}
        latest={latest}
        isGenerating={isGenerating}
        onRefresh={onRefreshProject}
      />

      <SceneCueSheet project={project} />

      {/* Right: settings — interim SettingsPanel mount until Task 8's
          SettingsInspector lands. */}
      <div className="w-[300px] shrink-0 overflow-y-auto border-l border-line bg-gutter">
        <SettingsPanel project={project} config={config} onRefresh={onRefreshProject} />
      </div>
    </div>
  )
}
