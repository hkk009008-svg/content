import type { Project } from '../../types/project'

interface Props {
  project: Project
}

export default function AssemblyGate({ project }: Props) {
  return (
    <div className="mt-6 p-6 bg-editorial-ready/5 border border-editorial-ready/20 rounded-xl text-center">
      <div className="text-3xl mb-3">🎬</div>
      <h2 className="text-xl font-bold text-editorial-ivory mb-2">Generation Complete</h2>
      <p className="text-sm text-editorial-ivory-mute mb-6">
        All scenes and shots have been generated, validated, and assembled.
      </p>

      <div className="flex justify-center gap-4">
        <a
          href={`/api/projects/${project.id}/export`}
          className="inline-flex items-center gap-2 bg-editorial-ready hover:bg-green-600 text-white
            px-8 py-3 rounded-lg font-medium text-sm transition-colors"
        >
          ⬇ Download Final Video
        </a>
      </div>

      <div className="mt-6 text-eyebrow-lg text-editorial-ivory-mute">
        <p>Pipeline stages: Style → Audio → Decompose → Director → Dialogue → Generate → Video → Interpolate → Assembly</p>
      </div>
    </div>
  )
}
