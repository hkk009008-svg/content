import type { ProgressEvent } from '../../types/project'
import { stageColors } from '../../lib/stageColors'

export interface NotesProps {
  notesBuffer: ProgressEvent[]
}

export default function Notes({ notesBuffer }: NotesProps) {
  return (
    <section className="px-6 py-6">
      <h2 className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute mb-3 font-console-mono">
        Notes
      </h2>
      <div
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-label="Director notes log"
        className="rounded border border-console-rule bg-console-surface p-3 space-y-0.5 max-h-48 overflow-y-auto"
      >
        {notesBuffer.length === 0 ? (
          <p className="font-console-mono text-xs text-console-ink-mute italic">
            Waiting for pipeline events…
          </p>
        ) : (
          notesBuffer.map((e, i) => (
            <div key={`${e.stage}-${e.shot_id ?? ''}-${e.percent ?? ''}-${i}`} className="flex gap-2 font-console-mono text-xs">
              <span className={`w-20 shrink-0 uppercase ${stageColors[e.stage] || 'text-console-ink-mute'}`}>
                [{e.stage}]
              </span>
              <span className="text-console-ink-dim truncate">{e.detail}</span>
            </div>
          ))
        )}
      </div>
    </section>
  )
}
