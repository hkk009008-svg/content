import type { Project } from '../../types/project'
import CapabilityConsole from '../console/CapabilityConsole'

/**
 * CapabilityPage (stub) — renders the existing `CapabilityConsole` (pipeline
 * scorecard). `onBack` is a no-op: navigation now lives in the always-mounted
 * `AppShell` page-bar (the Capability tab is one of four persistent tabs), so
 * the console's own back affordance has nothing to return to. Later tasks may
 * drop the console's internal back button entirely.
 */

interface Props {
  project: Project
}

export default function CapabilityPage({ project }: Props) {
  return (
    <div data-page="capability" className="h-full min-h-0 overflow-y-auto">
      <CapabilityConsole project={project} onBack={() => {}} />
    </div>
  )
}
