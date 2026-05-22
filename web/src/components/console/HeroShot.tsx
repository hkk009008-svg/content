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
      <section className="px-6 py-8 border-b border-console-rule flex items-center gap-6">
        <div className="w-40 aspect-video rounded border border-console-rule-strong bg-console-surface flex items-center justify-center text-xs text-console-ink-mute font-console-mono">
          no active shot
        </div>
        <div>
          <div className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute font-console-mono">Hero Shot</div>
          <div className="mt-1 text-sm text-console-ink-dim italic font-display">Waiting for pipeline to start…</div>
        </div>
      </section>
    )
  }

  return (
    <section className="px-6 py-6 border-b border-console-rule flex items-start gap-6">
      <div className="shrink-0 w-48 aspect-video rounded border border-console-rule-strong bg-console-surface overflow-hidden shadow-console-viewport">
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
          <div className="w-full h-full bg-console-render-fill flex items-center justify-center text-xs text-console-ink-mute font-console-mono">
            no take yet
          </div>
        )}
      </div>
      <div className="min-w-0">
        <div className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute font-console-mono">Hero Shot</div>
        <div className="mt-1 text-base font-display text-console-gold truncate italic">
          {scene?.title || 'Untitled scene'}
        </div>
        {shot.camera && (
          <div className="mt-1 text-xs text-console-ink-dim font-console-mono">
            <span className="uppercase tracking-wide text-console-ink-mute">Camera</span>{' '}
            <span>{shot.camera}</span>
          </div>
        )}
        {scene?.dialogue && (
          <div className="mt-1 text-xs text-console-ink-dim">
            <span className="uppercase tracking-wide text-console-ink-mute font-console-mono">Cue</span>{' '}
            <span className="italic font-display">{scene.dialogue.slice(0, 100)}</span>
          </div>
        )}
        <div className="mt-2 text-xs text-console-ink-dim line-clamp-2 font-display italic">{shot.prompt}</div>
      </div>
    </section>
  )
}
