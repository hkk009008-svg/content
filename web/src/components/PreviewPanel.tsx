import type { Project } from '../types/project'
import MediaAsset from './ui/MediaAsset'
import DeliverablesPanel from './DeliverablesPanel'

const API = '/api'

interface Props {
  project: Project
}

export default function PreviewPanel({ project }: Props) {
  return (
    <div className="p-4">
      <h2 className="text-sm font-semibold text-mut uppercase tracking-wider mb-3">Preview</h2>

      {/* Final Export */}
      <div className="mb-4">
        <MediaAsset
          key={`final-${project.id}`}
          kind="video"
          url={`${API}/projects/${project.id}/export`}
          className="w-full rounded-lg aspect-video"
          objectFit="contain"
          emptyLabel="Final video will appear here after generation."
          controls
        />
        <div className="flex justify-between items-center mt-2">
          <span className="text-eyebrow text-mut">Final Export</span>
          <a href={`${API}/projects/${project.id}/export`} download
            className="text-eyebrow text-mut hover:text-tx">
            Raw MP4
          </a>
        </div>
      </div>

      <DeliverablesPanel projectId={project.id} />

      {/* Per-Scene Previews */}
      {project.scenes.length > 0 && (
        <div>
          <h3 className="text-xs text-mut mb-2">Scene Previews</h3>
          <div className="space-y-2">
            {project.scenes.map((scene, idx) => (
              <div key={scene.id} className="bg-app border border-line rounded-lg overflow-hidden">
                <MediaAsset
                  kind="video"
                  url={`${API}/projects/${project.id}/preview/${scene.id}`}
                  className="w-full aspect-video"
                  objectFit="contain"
                  emptyLabel="Scene preview will appear here after generation."
                  controls
                />
                <div className="px-2 py-1.5 flex justify-between items-center">
                  <span className="text-eyebrow text-mut">
                    {idx + 1}. {scene.title}
                  </span>
                  <span className="text-eyebrow text-mut">
                    {scene.num_shots} shots / {scene.duration_seconds}s
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {project.scenes.length === 0 && (
        <p className="text-mut text-xs text-center py-8">
          Add scenes to preview generated footage.
        </p>
      )}
    </div>
  )
}
