import type { Scene, Shot, ShotState } from '../../types/project'
import { fileUrl } from '../../lib/mediaUrl'
import MediaAsset from '../ui/MediaAsset'

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
 * (video analogous), resolved through the projects file endpoint. Slice 10:
 * the resolved URL renders through MediaAsset, so a take whose stored path
 * can't be found (moved project, deleted file) shows an explicit missing
 * state instead of a blank/broken player -- "no shot selected" and "no take
 * yet" stay as their own distinct, pre-existing states above that.
 */
export default function ShotViewer({ projectId, shot, scene, shotState, apiBase }: Props) {
  // fileUrl defaults apiBase to '/api' itself -- an explicit `= ''` default
  // here would defeat that (see TakeStrip's identical note).
  const resolveMedia = (path: string) => fileUrl(apiBase, projectId, path)

  const imgUrl = shotState?.generated_image || shot?.generated_image || null
  const videoUrl = shotState?.generated_video || shot?.generated_video || null

  return (
    <div className="flex flex-1 min-h-0 flex-col border-b border-line bg-app">
      <div className="flex flex-1 min-h-0 items-center justify-center overflow-hidden bg-head p-4">
        {!shot ? (
          <div className="font-mono text-[11px] uppercase tracking-wide text-dim">No shot selected</div>
        ) : videoUrl ? (
          <MediaAsset
            key={videoUrl}
            kind="video"
            url={resolveMedia(videoUrl)}
            objectFit="contain"
            controls
            className="max-h-full max-w-full rounded border border-line"
          />
        ) : imgUrl ? (
          <MediaAsset
            key={imgUrl}
            kind="image"
            url={resolveMedia(imgUrl)}
            alt={shot.prompt?.slice(0, 80)}
            objectFit="contain"
            className="max-h-full max-w-full rounded border border-line"
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
