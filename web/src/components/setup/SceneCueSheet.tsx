import type { Project, Scene } from '../../types/project'
import { usePage } from '../../context/PageContext'
import { MICRO_LABEL, StatusDot, EmptyState, type Status } from '../ui'

/**
 * SceneCueSheet — Setup page center column. A dense read-mostly overview
 * table of `project.scenes`, distinct from `ScenePanel` (full CRUD, now
 * folded into `ProjectTree`'s left column): this is purely a navigation +
 * at-a-glance surface. Double-clicking a row jumps to the Edit page focused
 * on that scene (`usePage().setFocusScene` + `setPage('edit')`).
 *
 * Layout note (slice 13b): this column is a flex COLUMN, not a bare
 * scrolling block — a header, a scrollable table region, and a pinned
 * production-summary footer. The footer is what fills the "large unused
 * center space" the audit flagged: previously a short scene list left a
 * tall, silent `bg-app` void below it; now that space always anchors real
 * at-a-glance content (blocked/shot/runtime tallies) instead of nothing.
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

  const hasScenes = project.scenes.length > 0
  const blockedScenes = project.scenes.filter((s) => (s.shots?.length ?? 0) > 0).length
  const totalShots = project.scenes.reduce((sum, s) => sum + (s.num_shots || s.shots?.length || 0), 0)
  const generatedShots = project.scenes.reduce(
    (sum, s) => sum + (s.shots || []).filter((sh) => !!sh.generated_video).length,
    0,
  )
  const totalRuntime = project.scenes.reduce((sum, s) => sum + (s.duration_seconds || 0), 0)

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-app">
      <div className="border-b border-line px-3 py-2">
        <span className={MICRO_LABEL}>Scenes ({project.scenes.length})</span>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {!hasScenes ? (
          <div className="p-6">
            <EmptyState
              title="No scenes yet"
              message="Add a scene from the Scenes group in the left tree to start blocking shots."
              hint="Characters + locations first, then scenes"
            />
          </div>
        ) : (
          <table className="w-full border-collapse text-[11px] text-tx">
            <thead>
              <tr className="text-[10px] uppercase tracking-wide text-mut">
                <th className="sticky top-0 z-10 border-b border-line bg-panel px-3 py-1.5 text-left font-medium">#</th>
                <th className="sticky top-0 z-10 border-b border-line bg-panel px-3 py-1.5 text-left font-medium">Scene</th>
                <th className="sticky top-0 z-10 border-b border-line bg-panel px-3 py-1.5 text-left font-medium">Location</th>
                <th className="sticky top-0 z-10 border-b border-line bg-panel px-3 py-1.5 text-left font-medium">Shots</th>
                <th className="sticky top-0 z-10 border-b border-line bg-panel px-3 py-1.5 text-left font-medium">Primary API</th>
                <th className="sticky top-0 z-10 border-b border-line bg-panel px-3 py-1.5 text-left font-medium">Status</th>
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
                    <td className="px-3 py-1.5 font-mono text-mut">{idx + 1}</td>
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

      {/* Pinned production-summary footer — deliberate use of the column's
          remaining vertical space (audit: "large unused center space").
          Only meaningful once at least one scene exists; the empty state
          above already carries the full message when there are none. */}
      {hasScenes && (
        <div
          className="mt-auto flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line
                     bg-gutter px-3 py-2 font-mono text-[10px] uppercase tracking-wide text-mut"
        >
          <span>Aspect {project.global_settings?.aspect_ratio || '16:9'}</span>
          <span>{blockedScenes}/{project.scenes.length} scenes blocked</span>
          <span>{totalShots} shot{totalShots === 1 ? '' : 's'} planned</span>
          <span className={generatedShots > 0 ? 'text-ok' : undefined}>
            {generatedShots} generated
          </span>
          <span>~{Math.round(totalRuntime)}s runtime</span>
        </div>
      )}
    </div>
  )
}
