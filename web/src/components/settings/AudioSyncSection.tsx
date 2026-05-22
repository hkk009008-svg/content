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
        <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">Dialogue TTS Provider</label>
        <select
          value={s.tts_provider || 'ELEVENLABS_V3'}
          onChange={e => update('tts_provider', e.target.value)}
          className="w-full bg-editorial-ink border border-editorial-rule rounded-lg px-3 py-2 text-sm text-editorial-ivory">
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
        <p className="text-eyebrow-sm text-editorial-ivory-mute mt-0.5">Active TTS engine for dialogue + narration. Quality / latency / cost shown per option.</p>
      </div>

      {/* Quality enhancer toggles */}
      <div className="rounded-lg border border-editorial-rule bg-editorial-ink p-2 space-y-2">
        <span className="text-eyebrow text-editorial-ivory font-mono uppercase">Dialogue Quality Enhancers</span>
        {[
          { k: 'dialogue_mode_enabled', label: 'ElevenLabs Dialogue Mode', desc: 'Route multi-line dialogue through dedicated endpoint — natural turn-taking + prosody continuity.', def: true },
          { k: 'forced_alignment_enabled', label: 'Forced Alignment (WhisperX)', desc: 'Word-level timestamps + DTW correction. Lipsync accuracy ↑↑.', def: true },
          { k: 'room_tone_matching', label: 'Room Tone Matching', desc: 'Apply scene-environment reverb/EQ to dialogue. Sells the location.', def: false },
          { k: 'prosody_continuity', label: 'Prosody Continuity', desc: 'Smooth pitch/energy across dialogue turns — no abrupt voice resets.', def: true },
        ].map(t => (
          <div key={t.k} className="flex items-start gap-2">
            <input type="checkbox"
              checked={s[t.k] !== undefined ? s[t.k] : t.def}
              onChange={e => update(t.k, e.target.checked)}
              className="mt-0.5 accent-editorial-brass" />
            <div>
              <span className="text-eyebrow text-editorial-ivory font-medium">{t.label}</span>
              <p className="text-eyebrow-sm text-editorial-ivory-mute leading-tight">{t.desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Lipsync engine priority */}
      <div>
        <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">Lipsync Engine Priority</label>
        <div className="rounded-lg border border-editorial-rule bg-editorial-ink p-2 space-y-1">
          <LipsyncPriorityList s={s} config={config} update={update} />
          <p className="text-eyebrow-sm text-editorial-ivory-mute mt-1">Tried in order. First available engine wins. Hedra Character-3 is current SOTA for portrait talking heads.</p>
        </div>
      </div>

      {/* Lipsync validation gate */}
      <div className="rounded-lg border border-editorial-rule bg-editorial-ink p-2 space-y-2">
        <div className="flex items-center gap-2">
          <input type="checkbox"
            checked={s.lipsync_quality_validation !== false}
            onChange={e => update('lipsync_quality_validation', e.target.checked)}
            className="accent-editorial-brass" />
          <div>
            <span className="text-eyebrow text-editorial-ivory font-medium">Lipsync Quality Gate (SyncNet)</span>
            <p className="text-eyebrow-sm text-editorial-ivory-mute">Score lipsync output via SyncNet. Below threshold → escalate to next engine in priority list.</p>
          </div>
        </div>
        {s.lipsync_quality_validation !== false && (
          <div>
            <div className="flex justify-between text-eyebrow-sm text-editorial-ivory-mute mb-0.5">
              <span className="font-mono">SyncNet confidence threshold</span>
              <span className="text-editorial-brass font-bold">{(s.lipsync_validation_threshold ?? 0.65).toFixed(2)}</span>
            </div>
            <input type="range" min={0.3} max={0.95} step={0.05}
              value={s.lipsync_validation_threshold ?? 0.65}
              onChange={e => update('lipsync_validation_threshold', parseFloat(e.target.value))}
              aria-label="SyncNet confidence threshold"
              className="w-full accent-editorial-brass h-1" />
            <p className="text-eyebrow-sm text-editorial-ivory-mute">0.65 = "convincing in-context"; 0.85+ = "passes close-up scrutiny". Raise for hero shots, lower for B-roll.</p>
          </div>
        )}
      </div>

      {/* Music + foley providers */}
      <div className="grid grid-cols-1 gap-2">
        <ProviderSelect label="Music Provider" field="music_provider" modality="music" defaultValue="SUNO_V5"
          s={s} config={config} update={update} />
        <ProviderSelect label="Foley / SFX Provider" field="foley_provider" modality="foley" defaultValue="STABLE_AUDIO_FOLEY"
          s={s} config={config} update={update} />
      </div>

      {/* Purpose-based API matrix */}
      {(config as any)?.purpose_api_ranking && (config as any)?.purpose_tags && (
        <PurposeMatrix s={s} config={config} update={update} />
      )}
    </SettingsSection>
  )
}

function LipsyncPriorityList({ s, config, update }: { s: any; config: AppConfig | null; update: (k: string, v: any) => void | Promise<void> }) {
  const lipsyncDefault = ['HEDRA_C3', 'SYNC_SO_V3', 'MUSETALK', 'LATENTSYNC', 'OMNIHUMAN_V1_5', 'SYNC_V2']
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
          <div key={key} className="flex items-center gap-2 bg-editorial-ink-soft px-2 py-1.5 rounded border border-editorial-rule">
            <span className="text-eyebrow text-editorial-ivory-mute font-mono w-5">{idx + 1}.</span>
            <div className="flex-1">
              <span className="text-eyebrow text-editorial-ivory font-medium">{info?.label || key}</span>
              {info && (
                <span className="ml-1.5 text-eyebrow-sm text-editorial-ivory-mute">
                  Q{(info.quality_score ?? 0).toFixed(2)} · ${info.per_shot_cost?.toFixed(2)}
                </span>
              )}
            </div>
            <button type="button" aria-label={`Move ${info?.label || key} up`} onClick={() => move(idx, -1)} disabled={idx === 0}
              className="text-eyebrow text-editorial-ivory-mute hover:text-editorial-brass disabled:opacity-30 px-1">↑</button>
            <button type="button" aria-label={`Move ${info?.label || key} down`} onClick={() => move(idx, 1)} disabled={idx === priority.length - 1}
              className="text-eyebrow text-editorial-ivory-mute hover:text-editorial-brass disabled:opacity-30 px-1">↓</button>
          </div>
        )
      })}
    </>
  )
}

function ProviderSelect({ label, field, modality, defaultValue, s, config, update }: { label: string; field: string; modality: string; defaultValue: string; s: any; config: AppConfig | null; update: (k: string, v: any) => void | Promise<void> }) {
  return (
    <div>
      <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">{label}</label>
      <select value={s[field] || defaultValue}
        onChange={e => update(field, e.target.value)}
        className="w-full bg-editorial-ink border border-editorial-rule rounded-lg px-3 py-1.5 text-eyebrow text-editorial-ivory">
        {config?.api_registry && Object.entries(config.api_registry)
          .filter(([, v]: any) => v.modality === modality)
          .map(([k, v]: any) => (
            <option key={k} value={k} disabled={(v.status || 'live') === 'planned'}>
              {v.label} {v.status === 'planned' ? '[planned]' : v.status === 'beta' ? '[beta]' : ''}
            </option>
          ))}
      </select>
    </div>
  )
}

function PurposeMatrix({ s, config, update }: { s: any; config: AppConfig | null; update: (k: string, v: any) => void | Promise<void> }) {
  return (
    <div>
      <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">Purpose-Based Routing</label>
      <div className="rounded-lg border border-editorial-rule bg-editorial-ink overflow-hidden">
        <table className="w-full text-eyebrow">
          <tbody>
            {(config as any).purpose_tags.map((purpose: string) => {
              const ranking: string[] = (config as any).purpose_api_ranking[purpose] || []
              const override = (s.purpose_overrides || {})[purpose]
              const liveCandidates = ranking.filter(k => {
                const info = (config?.api_registry as any)?.[k]
                return info && (info.status || 'live') !== 'planned'
              })
              const chosen = override || liveCandidates[0] || ranking[0]
              const chosenInfo = (config?.api_registry as any)?.[chosen]
              return (
                <tr key={purpose} className="border-b border-editorial-rule/30 last:border-0">
                  <td className="px-2 py-1.5 text-editorial-ivory-mute font-mono">{purpose.replace(/_/g, ' ')}</td>
                  <td className="px-2 py-1.5">
                    <select
                      value={chosen}
                      aria-label={`API for ${purpose}`}
                      onChange={e => {
                        const next = { ...(s.purpose_overrides || {}), [purpose]: e.target.value }
                        if (!e.target.value) delete next[purpose]
                        update('purpose_overrides', next)
                      }}
                      className="w-full bg-editorial-ink-soft border border-editorial-rule rounded px-1.5 py-0.5 text-eyebrow text-editorial-ivory">
                      {ranking.map((k: string) => {
                        const info = (config?.api_registry as any)?.[k]
                        if (!info) return null
                        return (
                          <option key={k} value={k} disabled={(info.status || 'live') === 'planned'}>
                            {info.label} {info.status === 'planned' ? '[planned]' : info.status === 'beta' ? '[beta]' : ''}
                          </option>
                        )
                      })}
                    </select>
                  </td>
                  <td className="px-2 py-1.5 text-right text-editorial-ivory-mute">
                    {chosenInfo && (
                      <span className="font-mono">Q{(chosenInfo.quality_score ?? 0).toFixed(2)} · ${chosenInfo.per_shot_cost?.toFixed(2)}</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-eyebrow-sm text-editorial-ivory-mute mt-1">Per-purpose API picks. Defaults to the best available (live → beta → planned). Override per purpose to lock in a specific engine.</p>
    </div>
  )
}
