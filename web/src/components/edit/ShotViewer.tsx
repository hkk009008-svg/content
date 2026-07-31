import type { Scene, Shot, ShotState } from '../../types/project'
import { fileUrl } from '../../lib/mediaUrl'
import MediaAsset from '../ui/MediaAsset'

interface Props {
  projectId: string
  shot: Shot | null
  scene: Scene | null
  shotState: Partial<ShotState> | undefined
  apiBase?: string
  /** Slice 13c: navigate to the previous/next shot in project shot order
   *  (spans scene boundaries — the caller re-focuses the owning scene).
   *  Omit, or pair with the matching `has*Shot=false`, when there is no
   *  navigable neighbor; the button then renders `disabled` with a reason
   *  instead of silently doing nothing. */
  onPrevShot?: () => void
  onNextShot?: () => void
  hasPrevShot?: boolean
  hasNextShot?: boolean
}

/**
 * ShotViewer — the center stage. Media-resolution pattern reused verbatim
 * from `console/HeroShot.tsx`: `state?.generated_image || shot?.generated_image`
 * (video analogous), resolved through the projects file endpoint. Slice 10:
 * the resolved URL renders through MediaAsset, so a take whose stored path
 * can't be found (moved project, deleted file) shows an explicit missing
 * state instead of a blank/broken player -- "no shot selected" and "no take
 * yet" stay as their own distinct, pre-existing states above that.
 *
 * Transport bar (slice 13c): previously three purely decorative buttons
 * ("no playback engine yet"). Previous/Next are now wired to real shot
 * navigation and disable themselves (with an explicit reason) at either end
 * of the shot order. The former "Play" button is removed rather than
 * disabled forever -- a generated video already renders with the browser's
 * own `controls` transport (see `MediaAsset` below), so a second inert Play
 * affordance had no distinct behavior to wire.
 */
export default function ShotViewer({
  projectId,
  shot,
  scene,
  shotState,
  apiBase,
  onPrevShot,
  onNextShot,
  hasPrevShot = false,
  hasNextShot = false,
}: Props) {
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

      {/* Transport bar — Previous/Next shot navigation, real playback stays
          on the video element's own `controls` (wired above). */}
      <div className="flex flex-none items-center justify-center gap-4 border-t border-line bg-head px-4 py-2 font-mono text-[11px] text-mut">
        <button
          type="button"
          onClick={onPrevShot}
          disabled={!hasPrevShot || !onPrevShot}
          aria-label="Previous shot"
          title={hasPrevShot ? 'Previous shot' : 'Already at the first shot'}
          className="hover:text-tx disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:text-mut"
        >
          ⏮
        </button>
        <button
          type="button"
          onClick={onNextShot}
          disabled={!hasNextShot || !onNextShot}
          aria-label="Next shot"
          title={hasNextShot ? 'Next shot' : 'Already at the last shot'}
          className="hover:text-tx disabled:cursor-not-allowed disabled:opacity-30 disabled:hover:text-mut"
        >
          ⏭
        </button>
        <span className="text-dim">{scene?.title || 'Untitled scene'}</span>
      </div>
    </div>
  )
}
