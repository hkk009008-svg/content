import type { Project } from '../../types/project'
import CapabilityConsole from '../console/CapabilityConsole'

/**
 * CapabilityPage — renders the restyled `CapabilityConsole` (pipeline
 * scorecard). Navigation now lives in the always-mounted `AppShell`
 * page-bar (the Capability tab is one of four persistent tabs), so the
 * console's old `onBack` prop was dropped — there's nothing to return to
 * from inside the page itself.
 */

interface Props {
  project: Project
}

export default function CapabilityPage({ project }: Props) {
  return (
    <div data-page="capability" className="h-full min-h-0 overflow-y-auto bg-app text-tx">
      <CapabilityConsole project={project} />
    </div>
  )
}
