import type { AppConfig } from '../../types/project'
import { SettingsSection } from './SettingsSection'

interface Props {
  s: any
  config: AppConfig | null
  update: (key: string, value: any) => void | Promise<void>
}

export function AudioSyncSection({ s, config, update }: Props) {
  return (
    <SettingsSection title="Audio & Video Sync">
      {/* TTS provider selector */}
      <div>
        <label className="text-eyebrow text-tx block mb-1.5 uppercase tracking-wider">Dialogue TTS Provider</label>
        <select
          value={s.tts_provider || 'ELEVENLABS_V3'}
          onChange={e => update('tts_provider', e.target.value)}
          className="w-full bg-app border border-line rounded-lg px-3 py-2 text-sm text-tx">
          {config?.api_registry ? (
            <>
              {(['live', 'beta', 'planned'] as const).map((st) => {
                const ttsApis = Object.entries(config.api_registry).filter(
                  ([, v]: any) => v.modality === 'tts' && (v.status || 'live') === st,
                )
                if (ttsApis.length === 0) return null
                return (
                  <optgroup key={st} label={st === 'live' ? 'Live (production)' : st === 'beta' ? 'Beta (plumbed, untested)' : 'Planned (not yet wired)'}>
                    {ttsApis.map(([key, info]: any) => (
                      <option key={key} value={key} disabled={st === 'planned'}>
                        {info.label} — Q{(info.quality_score ?? 0).toFixed(2)} · ~{info.latency_s}s · ${info.per_shot_cost?.toFixed(3)}
                      </option>
                    ))}
                  </optgroup>
                )
              })}
            </>
          ) : (
            <option value="ELEVENLABS_V3">ElevenLabs v3 (current)</option>
          )}
        </select>
        <p className="text-eyebrow-sm text-mut mt-0.5">Active TTS engine for dialogue + narration. Quality / latency / cost shown per option.</p>
      </div>

      {/* Quality enhancer toggles */}
      <div className="rounded-lg border border-line bg-app p-2 space-y-2">
        <span className="text-eyebrow text-tx font-mono uppercase">Dialogue Quality Enhancers</span>
        {[
          { k: 'dialogue_mode_enabled', label: 'ElevenLabs Dialogue Mode', desc: 'Route multi-line dialogue through dedicated endpoint — natural turn-taking + prosody continuity.', def: true },
          { k: 'forced_alignment_enabled', label: 'Forced Alignment (WhisperX)', desc: 'Word-level timestamps + DTW correction. Lipsync accuracy ↑↑.', def: true },
        ].map(t => (
          <div key={t.k} className="flex items-start gap-2">
            <input type="checkbox"
              checked={s[t.k] !== undefined ? s[t.k] : t.def}
              onChange={e => update(t.k, e.target.checked)}
              className="mt-0.5 accent-acc" />
            <div>
              <span className="text-eyebrow text-tx font-medium">{t.label}</span>
              <p className="text-eyebrow-sm text-mut leading-tight">{t.desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Lipsync engine priority */}
      <div>
        <label className="text-eyebrow text-tx block mb-1.5 uppercase tracking-wider">Lipsync Engine Priority</label>
        <div className="rounded-lg border border-line bg-app p-2 space-y-1">
          <LipsyncPriorityList s={s} config={config} update={update} />
          <p className="text-eyebrow-sm text-mut mt-1">Tried in order. First available engine wins. Hedra Character-3 is current SOTA for portrait talking heads.</p>
        </div>
      </div>

      {/* Lipsync validation gate */}
      <div className="rounded-lg border border-line bg-app p-2 space-y-2">
        <div className="flex items-center gap-2">
          <input type="checkbox"
            checked={s.lipsync_quality_validation !== false}
            onChange={e => update('lipsync_quality_validation', e.target.checked)}
            className="accent-acc" />
          <div>
            <span className="text-eyebrow text-tx font-medium">Lipsync Quality Gate (SyncNet)</span>
            <p className="text-eyebrow-sm text-mut">Score lipsync output via SyncNet. Below threshold → escalate to next engine in priority list.</p>
          </div>
        </div>
        {s.lipsync_quality_validation !== false && (
          <div>
            <div className="flex justify-between text-eyebrow-sm text-mut mb-0.5">
              <span className="font-mono">SyncNet confidence threshold</span>
              <span className="text-acc font-bold">{(s.lipsync_validation_threshold ?? 0.65).toFixed(2)}</span>
            </div>
            <input type="range" min={0.3} max={0.95} step={0.05}
              value={s.lipsync_validation_threshold ?? 0.65}
              onChange={e => update('lipsync_validation_threshold', parseFloat(e.target.value))}
              aria-label="SyncNet confidence threshold"
              className="w-full accent-acc h-1" />
            <p className="text-eyebrow-sm text-mut">0.65 = "convincing in-context"; 0.85+ = "passes close-up scrutiny". Raise for hero shots, lower for B-roll.</p>
          </div>
        )}
      </div>

    </SettingsSection>
  )
}

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

