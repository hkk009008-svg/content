import type { Scene, Shot, ShotState } from '../../types/project'

interface Props {
  projectId: string
  shot: Shot | null
  scene: Scene | null
  shotState: Partial<ShotState> | undefined
  apiBase?: string
}

/**
 * ShotViewer — the center stage. Media-resolution pattern reused verbatim
 * from `console/HeroShot.tsx`: `state?.generated_image || shot?.generated_image`
 * (video analogous), resolved through the projects file endpoint.
 */
export default function ShotViewer({ projectId, shot, scene, shotState, apiBase = '' }: Props) {
  const base = apiBase || '/api'
  const resolveMedia = (path: string) => `${base}/projects/${projectId}/file?path=${encodeURIComponent(path)}`

  const imgUrl = shotState?.generated_image || shot?.generated_image || null
  const videoUrl = shotState?.generated_video || shot?.generated_video || null

  return (
    <div className="flex flex-1 min-h-0 flex-col border-b border-line bg-app">
      <div className="flex flex-1 min-h-0 items-center justify-center overflow-hidden bg-head p-4">
        {!shot ? (
          <div className="font-mono text-[11px] uppercase tracking-wide text-dim">No shot selected</div>
        ) : videoUrl ? (
          <video
            key={videoUrl}
            src={resolveMedia(videoUrl)}
            controls
            className="max-h-full max-w-full rounded border border-line object-contain"
          />
        ) : imgUrl ? (
          <img
            key={imgUrl}
            src={resolveMedia(imgUrl)}
            alt={shot.prompt?.slice(0, 80)}
            className="max-h-full max-w-full rounded border border-line object-contain"
          />
        ) : (
          <div className="font-mono text-[11px] uppercase tracking-wide text-dim">No take yet</div>
        )}
      </div>

      {/* Transport bar — presentational per brief (no playback engine yet). */}
      <div className="flex flex-none items-center justify-center gap-4 border-t border-line bg-head px-4 py-2 font-mono text-[11px] text-mut">
        <button type="button" className="hover:text-tx" aria-label="Previous frame" title="Previous frame">
          ⏮
        </button>
        <button type="button" className="hover:text-tx" aria-label="Play" title="Play">
          ▶
        </button>
        <button type="button" className="hover:text-tx" aria-label="Next frame" title="Next frame">
          ⏭
        </button>
        <span className="text-dim">{scene?.title || 'Untitled scene'}</span>
      </div>
    </div>
  )
}
