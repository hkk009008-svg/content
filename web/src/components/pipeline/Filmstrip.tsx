import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Project, ShotState } from '../../types/project'

/* ─── Mood palettes ─────────────────────────────────────────────────
   Nine editorial-cinema gradients lifted from the design comp.
   Cycled deterministically by shot index so the strip has visual
   variety without needing per-shot mood metadata from the backend. */
const MOOD_GRADIENTS = [
  // dawn — warm earth fade
  'linear-gradient(165deg, #3a2a1c 0%, #1a1612 60%, #0c0a08 100%)',
  // open — soft brass dusk
  'linear-gradient(165deg, #2c2218 0%, #1a1612 70%)',
  // brass — radial lamp pool
  'radial-gradient(ellipse at 50% 60%, #4d3621 0%, #1a120b 70%)',
  // watch — cool steel
  'linear-gradient(180deg, #1f2228 0%, #14171b 60%, #0c0a08 100%)',
  // paper — muted parchment
  'linear-gradient(160deg, #2a2520 0%, #1a1612 40%, #0e0c0a 100%)',
  // rain — blue twilight
  'linear-gradient(190deg, #1d2127 0%, #14171b 50%, #0c0a08 100%)',
  // stamp — radial ember
  'radial-gradient(ellipse at 50% 50%, #4a2a1c 0%, #14100c 75%)',
  // exit — fading dark
  'linear-gradient(200deg, #14171b 0%, #0a0908 100%)',
  // empty — flat near-black
  'linear-gradient(180deg, #14171b 0%, #0a0908 100%)',
] as const

const moodFor = (index: number) =>
  MOOD_GRADIENTS[index % MOOD_GRADIENTS.length]

const pad2 = (n: number) => n.toString().padStart(2, '0')

type FrameStatus = 'done' | 'active' | 'pending' | 'failed'

/* Map ShotStatus to a coarse frame status the strip cares about. */
function frameStatusOf(status: ShotState['status'] | undefined): FrameStatus {
  if (!status) return 'pending'
  if (status === 'failed') return 'failed'
  if (status === 'complete' || status === 'post_processing' || status === 'image_review') {
    return 'done'
  }
  if (
    status === 'generating_image' ||
    status === 'generating_video' ||
    status === 'plan_review' ||
    status === 'final_review'
  ) {
    return 'active'
  }
  return 'pending'
}

/** Extract a short engine tag (VEO, Kling, Sora, etc.) from a target_api string. */
function engineTag(targetApi: string | undefined, status: FrameStatus): string {
  if (status === 'active') return 'Live'
  if (status === 'pending') return '—'
  if (!targetApi) return '—'
  // Take the first segment up to the first underscore/dash, title-cased.
  const head = targetApi.split(/[_-]/)[0] ?? targetApi
  return head.charAt(0).toUpperCase() + head.slice(1).toLowerCase()
}

interface FrameEntry {
  shotId: string
  shotIndex: number       // 1-based, project-wide
  sceneOrder: number
  status: FrameStatus
  targetApi: string
  label: string           // short prompt / action summary
}

interface Props {
  project: Project
  shotStates: Map<string, Partial<ShotState>>
  activeShotId?: string | null
  onFrameSelect?: (shotId: string) => void
}

export default function Filmstrip({
  project,
  shotStates,
  activeShotId,
  onFrameSelect,
}: Props) {
  /* Flatten scenes → shots in playback order. Each frame gets a
     project-wide 1-based index for the sprocket-hole numbering. */
  const frames: FrameEntry[] = useMemo(() => {
    const ordered = project.scenes.slice().sort((a, b) => a.order - b.order)
    let runningIndex = 0
    const out: FrameEntry[] = []
    for (const scene of ordered) {
      for (const shot of scene.shots ?? []) {
        runningIndex += 1
        const state = shotStates.get(shot.id) as ShotState | undefined
        const status = frameStatusOf(state?.status)
        const label =
          shot.action_context?.trim() ||
          shot.prompt?.trim() ||
          'Untitled shot'
        out.push({
          shotId: shot.id,
          shotIndex: runningIndex,
          sceneOrder: scene.order,
          status,
          targetApi: shot.target_api ?? '',
          label: label.length > 80 ? label.slice(0, 77) + '…' : label,
        })
      }
    }
    return out
  }, [project.scenes, shotStates])

  /* Derive an internal "selected" frame for click-to-scrub, falling
     back to the active shot from props, then to the first active
     status frame, then to the first frame. */
  const [internalSelected, setInternalSelected] = useState<string | null>(null)
  const selectedId =
    internalSelected ??
    activeShotId ??
    frames.find(f => f.status === 'active')?.shotId ??
    frames[0]?.shotId ??
    null

  const handleSelect = useCallback(
    (shotId: string) => {
      setInternalSelected(shotId)
      onFrameSelect?.(shotId)
    },
    [onFrameSelect],
  )

  /* Keyboard scrubbing — ← / → cycle frames. Only fires when the
     strip itself or a child is focused, so we don't steal arrows
     from the rest of the page. */
  const stripRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const node = stripRef.current
    if (!node) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
      if (frames.length === 0) return
      const currentIdx = frames.findIndex(f => f.shotId === selectedId)
      const safeIdx = currentIdx === -1 ? 0 : currentIdx
      const nextIdx =
        e.key === 'ArrowRight'
          ? Math.min(frames.length - 1, safeIdx + 1)
          : Math.max(0, safeIdx - 1)
      const next = frames[nextIdx]
      if (next) {
        handleSelect(next.shotId)
        e.preventDefault()
        const el = node.querySelector<HTMLElement>(
          `[data-shot-id="${next.shotId}"]`,
        )
        el?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
      }
    }
    node.addEventListener('keydown', onKey)
    return () => node.removeEventListener('keydown', onKey)
  }, [frames, selectedId, handleSelect])

  const doneCount = frames.filter(f => f.status === 'done').length
  const activeCount = frames.filter(f => f.status === 'active').length
  const queuedCount = frames.filter(f => f.status === 'pending').length

  if (frames.length === 0) return null

  return (
    <section className="px-10 pt-8 pb-2 border-b border-editorial-rule">
      {/* Section label */}
      <div
        className="flex justify-between items-center pb-3 mb-4 border-b border-editorial-rule
                   font-mono text-eyebrow tracking-wide-eyebrow uppercase text-editorial-ivory-mute"
      >
        <span>Reels · All Shots</span>
        <span className="text-editorial-ivory-soft tabular-nums flex gap-3">
          <span>{pad2(doneCount)} Approved</span>
          {activeCount > 0 && (
            <span className="text-editorial-curtain">{pad2(activeCount)} Live</span>
          )}
          <span>{pad2(queuedCount)} Queued</span>
        </span>
      </div>

      {/* Filmstrip — black box with sprocket holes, horizontal scroll */}
      <div
        ref={stripRef}
        tabIndex={0}
        role="listbox"
        aria-label="Shot filmstrip — use left and right arrows to scrub"
        className="relative bg-black py-[18px] overflow-hidden
                   shadow-[inset_0_0_60px_rgba(0,0,0,0.8)]
                   focus:outline-none"
      >
        {/* Sprocket holes top + bottom */}
        <div
          className="absolute left-0 right-0 top-0 h-[18px] pointer-events-none"
          style={{
            backgroundImage:
              'repeating-linear-gradient(to right, transparent 0, transparent 14px, #0a0a0a 14px, #0a0a0a 22px, transparent 22px, transparent 44px)',
          }}
        />
        <div
          className="absolute left-0 right-0 bottom-0 h-[18px] pointer-events-none"
          style={{
            backgroundImage:
              'repeating-linear-gradient(to right, transparent 0, transparent 14px, #0a0a0a 14px, #0a0a0a 22px, transparent 22px, transparent 44px)',
          }}
        />

        <div className="flex gap-1.5 overflow-x-auto px-6 py-1.5">
          {frames.map((frame) => {
            const isSelected = frame.shotId === selectedId
            const isActive = frame.status === 'active'
            const isPending = frame.status === 'pending'
            const isFailed = frame.status === 'failed'

            return (
              <button
                key={frame.shotId}
                data-shot-id={frame.shotId}
                role="option"
                aria-selected={isSelected}
                onClick={() => handleSelect(frame.shotId)}
                className={`relative flex-none w-[132px] aspect-[9/16] overflow-hidden cursor-pointer
                            border bg-editorial-ink-soft p-0 transition-all duration-300
                            hover:-translate-y-1.5
                            ${isSelected || isActive
                              ? 'border-editorial-curtain shadow-[0_0_0_1px_#bf3737,0_0_28px_rgba(191,55,55,0.35)]'
                              : isFailed
                              ? 'border-editorial-curtain-deep'
                              : 'border-transparent hover:border-editorial-brass'}
                            ${isPending ? 'opacity-55' : ''}`}
              >
                {/* Mood gradient preview */}
                <div
                  className="absolute inset-0"
                  style={{
                    background: isPending
                      ? 'repeating-linear-gradient(45deg, #100c0a 0, #100c0a 6px, #181310 6px, #181310 12px)'
                      : moodFor(frame.shotIndex - 1),
                  }}
                  aria-hidden
                />

                {/* Shot number — top left */}
                <span
                  className="absolute top-2 left-2 z-10 px-1.5 py-[3px]
                             font-mono text-eyebrow-sm font-medium tracking-[0.14em]
                             text-editorial-ivory bg-black/70"
                >
                  {pad2(frame.shotIndex)}
                </span>

                {/* Engine tag — top right */}
                <span
                  className={`absolute top-2 right-2 z-10 px-1.5 py-[3px]
                              font-mono text-[7px] tracking-[0.18em] uppercase bg-black/70
                              ${isActive
                                ? 'text-editorial-curtain'
                                : isPending
                                ? 'text-editorial-ivory-faint'
                                : 'text-editorial-brass'}`}
                >
                  {engineTag(frame.targetApi, frame.status)}
                </span>

                {/* Caption — italic serif, fades in from bottom */}
                <span
                  className={`absolute bottom-0 left-0 right-0 z-10
                              px-2.5 pt-[26px] pb-2.5
                              font-display italic text-eyebrow-lg leading-snug
                              ${isPending ? 'text-editorial-ivory-faint' : 'text-editorial-ivory'}`}
                  style={{
                    fontVariationSettings: "'opsz' 14, 'SOFT' 60, 'wght' 380",
                    background:
                      'linear-gradient(to top, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.6) 60%, transparent 100%)',
                  }}
                >
                  {frame.label}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="font-mono text-eyebrow-sm tracking-wide-eyebrow uppercase
                      text-editorial-ivory-faint mt-2 text-right">
        ← / → to scrub
      </div>
    </section>
  )
}
