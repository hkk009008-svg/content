import type { Project, Scene } from '../../types/project'
import { usePage } from '../../context/PageContext'
import { MICRO_LABEL, StatusDot, type Status } from '../ui'

/**
 * SceneCueSheet — Setup page center column. A dense read-mostly overview
 * table of `project.scenes`, distinct from `ScenePanel` (full CRUD, now
 * folded into `ProjectTree`'s left column): this is purely a navigation +
 * at-a-glance surface. Double-clicking a row jumps to the Edit page focused
 * on that scene (`usePage().setFocusScene` + `setPage('edit')`).
 */

interface Props {
  project: Project
}

function locationName(project: Project, locationId: string): string {
  if (!locationId) return '—'
  return project.locations.find((l) => l.id === locationId)?.name || '—'
}

// Scene has no target_api of its own — read the first shot's override (the
// same field ScenePanel's per-shot picker writes), falling back to the
// system-chosen 'AUTO' label (mirrors `shot.target_api || 'AUTO'` in
// ScenePanel.tsx) when no shot exists yet or none is set.
function primaryApi(scene: Scene): string {
  return scene.shots?.find((s) => s.target_api)?.target_api || 'AUTO'
}

// Simple, data-only status: no shots decomposed yet = idle; all decomposed
// shots have a final video = ok; some progress (image or video) but not
// complete = run; decomposed with zero progress = idle.
function sceneStatus(scene: Scene): Status {
  const shots = scene.shots || []
  if (shots.length === 0) return 'idle'
  if (shots.every((s) => s.generated_video)) return 'ok'
  if (shots.some((s) => s.generated_video || s.generated_image)) return 'run'
  return 'idle'
}

export default function SceneCueSheet({ project }: Props) {
  const { setPage, setFocusScene } = usePage()

  const jumpToEdit = (sceneId: string) => {
    setFocusScene(sceneId)
    setPage('edit')
  }

  return (
    <div className="flex-1 min-w-0 overflow-y-auto bg-app">
      <div className="border-b border-line px-3 py-2">
        <span className={MICRO_LABEL}>Scenes ({project.scenes.length})</span>
      </div>

      {project.scenes.length === 0 ? (
        <div className="p-6 text-center text-[11px] text-mut">
          No scenes yet — add one from the Scenes group in the left tree.
        </div>
      ) : (
        <table className="w-full border-collapse text-[11px] text-tx">
          <thead>
            <tr className="border-b border-line bg-head text-[10px] uppercase tracking-wide text-mut">
              <th className="px-3 py-1.5 text-left font-medium">#</th>
              <th className="px-3 py-1.5 text-left font-medium">Scene</th>
              <th className="px-3 py-1.5 text-left font-medium">Location</th>
              <th className="px-3 py-1.5 text-left font-medium">Shots</th>
              <th className="px-3 py-1.5 text-left font-medium">Primary API</th>
              <th className="px-3 py-1.5 text-left font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {project.scenes.map((scene, idx) => {
              const shotCount = scene.num_shots || scene.shots?.length || 0
              return (
                <tr
                  key={scene.id}
                  onDoubleClick={() => jumpToEdit(scene.id)}
                  title="Double-click to open in Edit"
                  className="cursor-pointer border-b border-line hover:bg-panel"
                >
                  <td className="px-3 py-1.5 font-mono text-dim">{idx + 1}</td>
                  <td className="max-w-[220px] truncate px-3 py-1.5">{scene.title || 'Untitled scene'}</td>
                  <td className="px-3 py-1.5 text-mut">{locationName(project, scene.location_id)}</td>
                  <td className="px-3 py-1.5 font-mono">{shotCount}</td>
                  <td className="px-3 py-1.5 font-mono text-mut">{primaryApi(scene)}</td>
                  <td className="px-3 py-1.5">
                    <StatusDot status={sceneStatus(scene)} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
