import type { AppConfig } from '../../types/project'
import { SettingsSection } from './SettingsSection'

interface Props {
  s: any
  config: AppConfig | null
  update: (key: string, value: any) => void | Promise<void>
}

const API_DEFINITIONS = [
  {
    key: 'KLING_NATIVE', label: 'Kling 3.0', icon: '🎯', desc: 'Best faces — subject binding + face lock',
    controls: [
      { field: 'face_consistency', type: 'toggle', label: 'Face Consistency', desc: 'Kling face_consistency flag' },
      { field: 'storyboard_mode', type: 'toggle', label: 'Storyboard Mode', desc: 'Batch 6 shots in unified latent space' },
    ],
  },
  {
    key: 'SORA_NATIVE', label: 'Sora 2', icon: '🌊', desc: 'Best motion physics — cloth sim, body momentum',
    controls: [
      { field: 'duration', type: 'select', label: 'Duration', options: ['4', '8', '12', '16', '20'], desc: 'Seconds (strict values only)' },
      { field: 'resolution', type: 'select', label: 'Resolution', options: ['480p', '720p', '1080p'], desc: '' },
    ],
  },
  {
    key: 'VEO_NATIVE', label: 'Veo 3.1', icon: '🔮', desc: 'Reference images + native audio + first/last frame',
    controls: [
      { field: 'duration', type: 'select', label: 'Duration', options: ['5s', '6s', '8s'], desc: '' },
      { field: 'generate_audio', type: 'toggle', label: 'Native Audio', desc: 'Generate synced audio with video' },
    ],
  },
  {
    key: 'LTX', label: 'LTX 2.3', icon: '💰', desc: '4K support, cheapest, 15 camera motions',
    controls: [
      { field: 'resolution', type: 'select', label: 'Resolution', options: ['480p', '720p', '1080p', '4k'], desc: '' },
      { field: 'camera_motion_native', type: 'toggle', label: 'Native Camera Motion', desc: 'Use LTX 15 camera motion params' },
    ],
  },
  {
    key: 'RUNWAY_GEN4', label: 'Runway Gen-4', icon: '🎨', desc: 'Style lock with reference images',
    controls: [],
  },
] as const

export function ApiEnginesSection({ s, config, update }: Props) {
  return (
    <SettingsSection title="API Engines">
      <p className="text-eyebrow-sm text-editorial-ivory-mute mb-2">Enable/disable video APIs and control their per-engine settings. Disabled APIs are skipped in the cascade.</p>

      {/* Cascade Retry Limit */}
      <div>
        <div className="flex justify-between text-eyebrow text-editorial-ivory-mute mb-0.5">
          <span className="font-mono">Cascade retry cycles</span>
          <span className="text-editorial-brass font-bold">{s.cascade_retry_limit ?? 2}</span>
        </div>
        <input type="range" min={0} max={5} step={1}
          value={s.cascade_retry_limit ?? 2}
          onChange={e => update('cascade_retry_limit', parseInt(e.target.value))}
          aria-label="Cascade retry cycles"
          className="w-full accent-editorial-brass h-1" />
        <p className="text-eyebrow-sm text-editorial-ivory-mute">Full cascade retries before giving up. 0 = no retries, 2 = default.</p>
      </div>

      {/* API Engine Cards */}
      {API_DEFINITIONS.map(api => {
        const engines = s.api_engines || {}
        const eng = engines[api.key] || config?.api_engine_defaults?.[api.key] || { enabled: true }
        const updateEngine = (field: string, value: any) => {
          const current = s.api_engines || config?.api_engine_defaults || {}
          update('api_engines', { ...current, [api.key]: { ...current[api.key], ...eng, [field]: value } })
        }
        return (
          <div key={api.key} className={`bg-editorial-ink border rounded-lg p-3 transition-all ${
            eng.enabled !== false ? 'border-editorial-brass/30' : 'border-editorial-rule opacity-60'}`}>
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-sm">{api.icon}</span>
                <span className="text-eyebrow-lg text-editorial-ivory font-bold">{api.label}</span>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" checked={eng.enabled !== false}
                  onChange={e => updateEngine('enabled', e.target.checked)}
                  aria-label={`Enable ${api.label}`}
                  className="sr-only peer" />
                <div className="w-8 h-4 bg-editorial-rule rounded-full peer peer-checked:bg-editorial-brass
                  after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full
                  after:h-3 after:w-3 after:transition-all peer-checked:after:translate-x-full" />
              </label>
            </div>
            <p className="text-eyebrow-sm text-editorial-ivory-mute mb-2">{api.desc}</p>
            {eng.enabled !== false && api.controls.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-editorial-rule">
                {api.controls.map((ctrl: any) => (
                  <div key={ctrl.field}>
                    {ctrl.type === 'toggle' ? (
                      <div className="flex items-center gap-2">
                        <input type="checkbox" checked={eng[ctrl.field] !== false}
                          onChange={e => updateEngine(ctrl.field, e.target.checked)}
                          aria-label={ctrl.label}
                          className="accent-editorial-brass" />
                        <span className="text-eyebrow text-editorial-ivory">{ctrl.label}</span>
                        {ctrl.desc && <span className="text-eyebrow-sm text-editorial-ivory-mute">— {ctrl.desc}</span>}
                      </div>
                    ) : ctrl.type === 'select' ? (
                      <div className="flex items-center gap-2">
                        <span className="text-eyebrow text-editorial-ivory-mute font-mono w-20">{ctrl.label}</span>
                        <select value={eng[ctrl.field] || ctrl.options[0]}
                          onChange={e => updateEngine(ctrl.field, e.target.value)}
                          aria-label={ctrl.label}
                          className="flex-1 bg-editorial-ink-soft border border-editorial-rule rounded px-2 py-1 text-eyebrow text-editorial-ivory">
                          {ctrl.options.map((opt: string) => <option key={opt} value={opt}>{opt}</option>)}
                        </select>
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </SettingsSection>
  )
}
