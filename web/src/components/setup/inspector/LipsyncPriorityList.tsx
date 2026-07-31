import type { AppConfig } from '../../../types/project'

/**
 * Reorderable lipsync-engine cascade. Writes the `lipsync_engine_priority`
 * settings key (a string list, server-validated in `web_server.py`'s
 * `_SETTINGS_KEY_VALIDATORS`), consumed by `VoiceSection`.
 *
 * Extracted from the since-deleted `settings/AudioSyncSection.tsx`, whose
 * section component was unmounted by the Resolve-style redesign while this
 * list stayed live.
 */
export function LipsyncPriorityList({ s, config, update }: { s: any; config: AppConfig | null; update: (k: string, v: any) => void | Promise<void> }) {
  const lipsyncDefault = ['SYNC_SO_V3', 'MUSETALK', 'LATENTSYNC', 'OMNIHUMAN_V1_5', 'SYNC_V2']
  const priority: string[] = s.lipsync_engine_priority || lipsyncDefault
  const setPriority = (next: string[]) => update('lipsync_engine_priority', next)
  const move = (idx: number, dir: -1 | 1) => {
    const j = idx + dir
    if (j < 0 || j >= priority.length) return
    const next = [...priority]
    ;[next[idx], next[j]] = [next[j], next[idx]]
    setPriority(next)
  }
  return (
    <>
      {priority.map((key, idx) => {
        const info = (config?.api_registry as any)?.[key]
        return (
          <div key={key} className="flex items-center gap-2 bg-panel px-2 py-1.5 rounded border border-line">
            <span className="text-eyebrow text-mut font-mono w-5">{idx + 1}.</span>
            <div className="flex-1">
              <span className="text-eyebrow text-tx font-medium">{info?.label || key}</span>
              {info && (
                <span className="ml-1.5 text-eyebrow-sm text-mut">
                  Q{(info.quality_score ?? 0).toFixed(2)} · ${info.per_shot_cost?.toFixed(2)}
                </span>
              )}
            </div>
            <button type="button" aria-label={`Move ${info?.label || key} up`} onClick={() => move(idx, -1)} disabled={idx === 0}
              className="text-eyebrow text-mut hover:text-acc disabled:opacity-30 px-1">↑</button>
            <button type="button" aria-label={`Move ${info?.label || key} down`} onClick={() => move(idx, 1)} disabled={idx === priority.length - 1}
              className="text-eyebrow text-mut hover:text-acc disabled:opacity-30 px-1">↓</button>
          </div>
        )
      })}
    </>
  )
}
