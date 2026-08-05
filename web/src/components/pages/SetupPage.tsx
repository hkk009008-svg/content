import type { Project, AppConfig, ProgressEvent } from '../../types/project'
import ProjectTree from '../setup/ProjectTree'
import SceneCueSheet from '../setup/SceneCueSheet'
import SettingsInspector from '../setup/SettingsInspector'

/**
 * SetupPage — 3-column Resolve-style layout: `ProjectTree | SceneCueSheet |
 * SettingsInspector`. Replaces the flat 3-col-grid stub (which mounted the
 * six workshop panels unchanged) now that the left column has its own tree
 * shell and the center has a real scenes cue sheet.
 *
 * The right column is the reconciled `SettingsInspector` (Task 8):
 * Project → Video → Image → Identity → Voice → Budget, Google-first engines,
 * local/cloud badges, no retired quality-tier controls.
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

      {/* Right: reconciled settings inspector. Narrower below the `xl`
          breakpoint so the 3-column shell stays legible down to 1024px
          instead of assuming a >=1440px floor. */}
      <div className="w-[264px] shrink-0 overflow-y-auto border-l border-line bg-gutter xl:w-[300px]">
        <SettingsInspector project={project} config={config} onRefresh={onRefreshProject} />
      </div>
    </div>
  )
}
