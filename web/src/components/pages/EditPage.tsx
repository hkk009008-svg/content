import type { Project } from '../../types/project'
import { LoadingState } from '../ui'

/**
 * EditPage (stub) — placeholder for the redesigned scene-editing surface
 * (Task 6 gives it the scene list + `focusScene` jump behavior). For now it
 * renders a `LoadingState` placeholder so the page-bar tab is reachable and
 * the shell switch has a fourth target without pulling in real logic yet.
 */

interface Props {
  project: Project
}

export default function EditPage({ project }: Props) {
  return (
    <div
      data-page="edit"
      className="h-full min-h-0 flex flex-col items-center justify-center bg-app text-tx gap-3"
    >
      <LoadingState label="Editor — coming next pass" size="lg" />
      <div className="font-mono text-[10px] uppercase tracking-wide text-dim">
        {project.scenes.length} scene{project.scenes.length === 1 ? '' : 's'} in the reel
      </div>
    </div>
  )
}
