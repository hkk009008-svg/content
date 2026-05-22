import { useMemo } from 'react'
import type { Project, ShotState } from '../../types/project'

export interface HeroShotProps {
  project: Project
  activeShotId: string | null
  shotStates: Map<string, Partial<ShotState>>
  apiBase?: string
  projectId?: string | null
}

export default function HeroShot({
  project,
  activeShotId,
  shotStates,
  apiBase = '',
  projectId,
}: HeroShotProps) {
  const base = apiBase || '/api'

  const { shot, scene } = useMemo(() => {
    if (!activeShotId) return { shot: null, scene: null }
    for (const sc of project?.scenes || []) {
      for (const sh of sc.shots || []) {
        if (sh.id === activeShotId) return { shot: sh, scene: sc }
      }
    }
    return { shot: null, scene: null }
  }, [activeShotId, project])

  const state = activeShotId ? shotStates.get(activeShotId) : null
  const imgUrl = state?.generated_image || shot?.generated_image || null
  const videoUrl = state?.generated_video || shot?.generated_video || null

  const resolveMedia = (path: string) =>
    projectId
      ? `${base}/projects/${projectId}/file?path=${encodeURIComponent(path)}`
      : path

  if (!activeShotId || !shot) {
    return (
      <section className="px-6 py-8 border-b border-editorial-rule flex items-center gap-6">
        <div className="w-40 aspect-video rounded border border-editorial-rule bg-editorial-ink flex items-center justify-center text-xs text-editorial-ivory-mute">
          no active shot
        </div>
        <div>
          <div className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute">Hero Shot</div>
          <div className="mt-1 text-sm text-editorial-ivory-mute italic">Waiting for pipeline to start…</div>
        </div>
      </section>
    )
  }

  return (
    <section className="px-6 py-6 border-b border-editorial-rule flex items-start gap-6">
      <div className="shrink-0 w-48 aspect-video rounded border border-editorial-rule bg-editorial-ink overflow-hidden">
        {videoUrl ? (
          <video
            src={resolveMedia(videoUrl)}
            autoPlay
            muted
            loop
            className="w-full h-full object-cover"
          />
        ) : imgUrl ? (
          <img
            src={resolveMedia(imgUrl)}
            className="w-full h-full object-cover"
            alt={shot.prompt?.slice(0, 80)}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-xs text-editorial-ivory-mute">
            no take yet
          </div>
        )}
      </div>
      <div className="min-w-0">
        <div className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute">Hero Shot</div>
        <div className="mt-1 text-base font-semibold text-editorial-brass truncate">
          {scene?.title || 'Untitled scene'}
        </div>
        {shot.camera && (
          <div className="mt-1 text-xs text-editorial-ivory-mute">
            <span className="uppercase tracking-wide">Camera</span>{' '}
            <span className="font-mono">{shot.camera}</span>
          </div>
        )}
        {scene?.dialogue && (
          <div className="mt-1 text-xs text-editorial-ivory-mute">
            <span className="uppercase tracking-wide">Cue</span>{' '}
            <span className="italic">{scene.dialogue.slice(0, 100)}</span>
          </div>
        )}
        <div className="mt-2 text-xs text-editorial-ivory-mute line-clamp-2">{shot.prompt}</div>
      </div>
    </section>
  )
}
