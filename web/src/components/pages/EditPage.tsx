import { useMemo, useState } from 'react'
import type { AppConfig, Project, ShotState } from '../../types/project'
import { usePage } from '../../context/PageContext'
import ShotBin from '../edit/ShotBin'
import ShotViewer from '../edit/ShotViewer'
import Timeline from '../edit/Timeline'
import ShotInspector from '../edit/ShotInspector'

interface Props {
  project: Project
  config: AppConfig | null
  apiBase: string
  onRefreshProject: () => Promise<void> | void
  shotStates: Map<string, Partial<ShotState>>
}

/**
 * EditPage — the shot workspace. 3 regions: `ShotBin (left)` | center stage
 * (`ShotViewer` + transport + `Timeline`) | `ShotInspector (right)`.
 *
 * The focused scene defaults to `usePage().focusScene ?? project.scenes[0]?.id`
 * (Task 6's scene-jump lands here). `selectedShotId` is local state, defaulting
 * to the focused scene's first shot. Selecting a Timeline clip from a
 * DIFFERENT scene also re-focuses that scene (via `setFocusScene`) so
 * `ShotBin` follows the Timeline selection across scene boundaries too.
 */
export default function EditPage({ project, config, apiBase, onRefreshProject, shotStates }: Props) {
  const { focusScene, setFocusScene } = usePage()

  const sceneId = focusScene ?? project.scenes[0]?.id ?? null
  const scene = useMemo(() => project.scenes.find((s) => s.id === sceneId) ?? null, [project.scenes, sceneId])

  const [selectedShotId, setSelectedShotId] = useState<string | null>(null)

  const activeShotId = useMemo(() => {
    if (selectedShotId && scene?.shots?.some((sh) => sh.id === selectedShotId)) return selectedShotId
    return scene?.shots?.[0]?.id ?? null
  }, [selectedShotId, scene])

  const active = useMemo(() => {
    for (const sc of project.scenes) {
      const found = sc.shots?.find((sh) => sh.id === activeShotId)
      if (found) return { shot: found, scene: sc }
    }
    return { shot: null, scene: null }
  }, [project.scenes, activeShotId])

  const handleSelectShot = (shotId: string) => {
    setSelectedShotId(shotId)
    const owningScene = project.scenes.find((sc) => sc.shots?.some((sh) => sh.id === shotId))
    if (owningScene && owningScene.id !== sceneId) setFocusScene(owningScene.id)
  }

  return (
    <div data-page="edit" className="flex h-full min-h-0 bg-app text-tx">
      <ShotBin scene={scene} shotStates={shotStates} activeShotId={activeShotId} onSelectShot={handleSelectShot} />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <ShotViewer
          projectId={project.id}
          shot={active.shot}
          scene={active.scene}
          shotState={activeShotId ? shotStates.get(activeShotId) : undefined}
          apiBase={apiBase}
        />
        <Timeline project={project} shotStates={shotStates} activeShotId={activeShotId} onSelect={handleSelectShot} />
      </div>

      <ShotInspector
        project={project}
        config={config}
        scene={active.scene}
        shot={active.shot}
        shotState={activeShotId ? shotStates.get(activeShotId) : undefined}
        apiBase={apiBase}
        onRefreshProject={onRefreshProject}
      />
    </div>
  )
}
