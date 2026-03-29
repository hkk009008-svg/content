import type { Project } from '../../types/project'

interface Props {
  project: Project
}

export default function AssemblyGate({ project }: Props) {
  return (
    <div className="mt-6 p-6 bg-cinema-success/5 border border-cinema-success/20 rounded-xl text-center">
      <div className="text-3xl mb-3">🎬</div>
      <h2 className="text-xl font-bold text-cinema-text mb-2">Generation Complete</h2>
      <p className="text-sm text-cinema-muted mb-6">
        All scenes and shots have been generated, validated, and assembled.
      </p>

      <div className="flex justify-center gap-4">
        <a
          href={`/api/projects/${project.id}/export`}
          className="inline-flex items-center gap-2 bg-cinema-success hover:bg-green-600 text-white
            px-8 py-3 rounded-lg font-medium text-sm transition-colors"
        >
          ⬇ Download Final Video
        </a>
      </div>

      <div className="mt-6 text-[11px] text-cinema-muted">
        <p>Pipeline stages: Style → Audio → Decompose → Director → Dialogue → Generate → Video → Interpolate → Assembly</p>
      </div>
    </div>
  )
}
