import type { ProgressEvent } from '../../types/project'
import { stageColors } from '../../lib/stageColors'

export interface NotesProps {
  notesBuffer: ProgressEvent[]
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
            <div key={`${e.stage}-${e.shot_id ?? ''}-${e.percent ?? ''}-${i}`} className="flex gap-2 font-mono text-xs">
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
