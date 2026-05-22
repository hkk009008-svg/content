import type { ProgressEvent } from '../../types/project'

export interface NotesProps {
  notesBuffer: ProgressEvent[]
}

// Replicated from GenerationPanel — stage name → Tailwind text color
const stageColors: Record<string, string> = {
  STYLE: 'text-purple-400',
  AUDIO: 'text-blue-400',
  SCENE: 'text-editorial-brass',
  DECOMPOSE: 'text-cyan-400',
  DIALOGUE: 'text-pink-400',
  GENERATE: 'text-yellow-400',
  VIDEO: 'text-orange-400',
  VALIDATED: 'text-editorial-ready',
  IDENTITY_FAIL: 'text-editorial-curtain',
  RETRY: 'text-editorial-warn',
  ASSEMBLY: 'text-indigo-400',
  COMPLETE: 'text-editorial-ready',
  DONE: 'text-editorial-ready',
  ERROR: 'text-editorial-curtain',
  CANCELLED: 'text-editorial-ivory-mute',
  WARNING: 'text-editorial-warn',
  KEYFRAME: 'text-yellow-400',
  KEYFRAME_READY: 'text-editorial-ready',
  KEYFRAME_REVIEW: 'text-editorial-brass',
  MOTION: 'text-orange-400',
  MOTION_READY: 'text-editorial-ready',
  PERFORMANCE: 'text-pink-400',
  REVIEW: 'text-editorial-brass',
  PLAN_REVIEW: 'text-cyan-400',
  DIRECTOR: 'text-purple-400',
  SHOT_FAILED: 'text-editorial-curtain',
  PAUSED: 'text-editorial-warn',
  RESUMED: 'text-editorial-ready',
}

export default function Notes({ notesBuffer }: NotesProps) {
  return (
    <section className="px-6 py-6">
      <h2 className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute mb-3">
        Notes
      </h2>
      <div
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-label="Director notes log"
        className="rounded border border-editorial-rule bg-editorial-ink p-3 space-y-0.5 max-h-48 overflow-y-auto"
      >
        {notesBuffer.length === 0 ? (
          <p className="font-mono text-xs text-editorial-ivory-mute italic">
            Waiting for pipeline events…
          </p>
        ) : (
          notesBuffer.map((e, i) => (
            <div key={i} className="flex gap-2 font-mono text-xs">
              <span className={`w-20 shrink-0 uppercase ${stageColors[e.stage] || 'text-editorial-ivory-mute'}`}>
                [{e.stage}]
              </span>
              <span className="text-editorial-ivory-mute truncate">{e.detail}</span>
            </div>
          ))
        )}
      </div>
    </section>
  )
}
