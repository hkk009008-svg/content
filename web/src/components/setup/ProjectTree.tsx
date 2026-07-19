import type { Project, AppConfig, ProgressEvent } from '../../types/project'
import { MICRO_LABEL } from '../ui'
import CharacterPanel from '../CharacterPanel'
import LocationPanel from '../LocationPanel'
import ObjectPanel from '../ObjectPanel'
import ScenePanel from '../ScenePanel'
import GenerationPanel from '../GenerationPanel'
import PreviewPanel from '../PreviewPanel'

/**
 * ProjectTree — Setup page left column (Resolve-style "bin"). A token-styled
 * shell around the four existing CRUD panels (Characters / Locations /
 * Objects / Scenes), each of which already owns its own collapsible header
 * + counts, so nesting them under a second disclosure control would just
 * double the chrome. Per the Task 6 brief, this restyles/relocates the
 * panels into the tree column WITHOUT touching their internal logic — props
 * are forwarded verbatim.
 *
 * Generation + Preview (no longer reachable from a mid-run pipeline screen
 * once Setup owns the 3-col layout) fold into the tree footer so operators
 * can still start a run / check exports without leaving Setup.
 */

interface Props {
  project: Project
  config: AppConfig | null
  events: ProgressEvent[]
  latest: ProgressEvent | null
  isGenerating: boolean
  onRefresh: () => Promise<void> | void
}

export default function ProjectTree({
  project,
  config,
  events,
  latest,
  isGenerating,
  onRefresh,
}: Props) {
  return (
    <div className="flex w-[236px] shrink-0 flex-col overflow-y-auto border-r border-line bg-gutter">
      <div className="border-b border-line px-3 py-2">
        <span className={MICRO_LABEL}>Project</span>
      </div>

      <div className="border-b border-line">
        <CharacterPanel project={project} config={config} onRefresh={onRefresh} />
      </div>
      <div className="border-b border-line">
        <LocationPanel project={project} config={config} onRefresh={onRefresh} />
      </div>
      <div className="border-b border-line">
        <ObjectPanel project={project} onRefresh={onRefresh} />
      </div>
      <div className="border-b border-line">
        <ScenePanel project={project} config={config} onRefresh={onRefresh} />
      </div>

      {/* Footer — Generation + Preview access, folded in so both stay
          reachable from Setup (previously mid-column panels in the stub). */}
      <div className="mt-auto">
        <div className="border-t border-line">
          <GenerationPanel
            project={project}
            events={events}
            latest={latest}
            isGenerating={isGenerating}
          />
        </div>
        <div className="border-t border-line">
          <PreviewPanel project={project} />
        </div>
      </div>
    </div>
  )
}
