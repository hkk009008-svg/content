import { SettingsSection } from './SettingsSection'

interface Props {
  s: any
  update: (key: string, value: any) => void | Promise<void>
}

export function PostProcessingSection({ s, update }: Props) {
  return (
    <SettingsSection title="Post-Processing">
      {/* Color Grade Preset */}
      <div>
        <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">Color Grade</label>
        <select value={s.color_grade_preset || 'warm_cinema'} onChange={e => update('color_grade_preset', e.target.value)}
          className="w-full bg-editorial-ink border border-editorial-rule rounded-lg px-3 py-2 text-sm text-editorial-ivory">
          <option value="warm_cinema">Warm Cinema — amber highlights, rich shadows</option>
          <option value="cool_noir">Cool Noir — blue shadows, desaturated</option>
          <option value="vibrant">Vibrant — punchy saturation</option>
          <option value="desaturated">Desaturated — muted, washed</option>
          <option value="golden_hour">Golden Hour — warm amber glow</option>
          <option value="moonlight">Moonlight — cool blue, dim</option>
          <option value="high_contrast">High Contrast — crushed blacks, bright highs</option>
          <option value="pastel">Pastel — lifted blacks, soft</option>
        </select>
        <p className="text-eyebrow-sm text-editorial-ivory-mute mt-0.5">Applied to final assembly. Auto-mapped from mood if not set.</p>
      </div>

      {/* Lip Sync Mode */}
      <div>
        <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">Lip Sync Mode</label>
        <select value={s.lip_sync_mode || 'auto'} onChange={e => update('lip_sync_mode', e.target.value)}
          className="w-full bg-editorial-ink border border-editorial-rule rounded-lg px-3 py-2 text-sm text-editorial-ivory">
          <option value="auto">Auto — AI analyzes shot type + dialogue length</option>
          <option value="overlay">Overlay (MuseTalk) — preserves camera work, replaces mouth only</option>
          <option value="generation">Generation (Omnihuman) — full talking head from still</option>
          <option value="skip">Skip — no lip sync</option>
        </select>
      </div>

      {/* Face Swap toggle (FAL PixVerse post-video) */}
      <ToggleCard field="face_swap_enabled" label="Face Swap" desc="FAL PixVerse post-video" s={s} update={update} />

      {/* Motion Quality Gate */}
      <Slider label="Motion quality gate" field="motion_quality_threshold" s={s} update={update}
        min={0} max={1} step={0.05} defaultValue={0.4}
        hint="Min smoothness score to accept video. Below threshold → auto RIFE or regenerate." />

      {/* Coherence Check Toggle */}
      <div className="flex items-center gap-2 bg-editorial-ink rounded-lg px-3 py-2 border border-editorial-rule">
        <input type="checkbox"
          checked={s.coherence_check_enabled !== false}
          onChange={e => update('coherence_check_enabled', e.target.checked)}
          className="accent-editorial-brass" />
        <div>
          <span className="text-eyebrow text-editorial-ivory font-medium">Coherence Analysis</span>
          <p className="text-eyebrow-sm text-editorial-ivory-mute">Color/lighting/composition consistency between shots</p>
        </div>
      </div>

      {/* Location Research Toggle */}
      <div className="flex items-center gap-2 bg-editorial-ink rounded-lg px-3 py-2 border border-editorial-rule">
        <input type="checkbox"
          checked={s.location_research === true}
          onChange={e => update('location_research', e.target.checked)}
          className="accent-editorial-brass" />
        <div>
          <span className="text-eyebrow text-editorial-ivory font-medium">Location Research</span>
          <p className="text-eyebrow-sm text-editorial-ivory-mute">Auto-fetch real location reference photos via web search (Tavily) — supplements uploads</p>
        </div>
      </div>

      {/* Color Drift Sensitivity */}
      {s.coherence_check_enabled !== false && (
        <Slider label="Color drift sensitivity" field="color_drift_sensitivity" s={s} update={update}
          min={0.1} max={0.5} step={0.05} defaultValue={0.3}
          hint="Max color histogram drift before triggering prompt adjustment. Lower = stricter." />
      )}

      {/* Scene Transitions Toggle */}
      <div className="flex items-center gap-2 bg-editorial-ink rounded-lg px-3 py-2 border border-editorial-rule">
        <input type="checkbox"
          checked={s.scene_transitions === true}
          onChange={e => update('scene_transitions', e.target.checked)}
          className="accent-editorial-brass" />
        <div>
          <span className="text-eyebrow text-editorial-ivory font-medium">Scene Transitions</span>
          <p className="text-eyebrow-sm text-editorial-ivory-mute">Cross-dissolve between scenes (re-encodes on assembly)</p>
        </div>
      </div>

      {/* Transition Duration */}
      {s.scene_transitions === true && (
        <Slider label="Transition duration (s)" field="transition_duration" s={s} update={update}
          min={0.2} max={2.0} step={0.1} defaultValue={0.5}
          hint="Length of the cross-dissolve in seconds." />
      )}
    </SettingsSection>
  )
}

function ToggleCard({ field, label, desc, s, update }: { field: string; label: string; desc: string; s: any; update: (k: string, v: any) => void | Promise<void> }) {
  return (
    <div className="flex items-center gap-2 bg-editorial-ink rounded-lg px-3 py-2 border border-editorial-rule">
      <input type="checkbox"
        checked={s[field] !== false}
        onChange={e => update(field, e.target.checked)}
        className="accent-editorial-brass"
        aria-label={label} />
      <div>
        <span className="text-eyebrow text-editorial-ivory font-medium">{label}</span>
        <p className="text-eyebrow-sm text-editorial-ivory-mute">{desc}</p>
      </div>
    </div>
  )
}

function Slider({ label, field, s, update, min, max, step, defaultValue, hint }: { label: string; field: string; s: any; update: (k: string, v: any) => void | Promise<void>; min: number; max: number; step: number; defaultValue: number; hint: string }) {
  const value = s[field] ?? defaultValue
  return (
    <div>
      <div className="flex justify-between text-eyebrow text-editorial-ivory-mute mb-0.5">
        <span className="font-mono">{label}</span>
        <span className="text-editorial-brass font-bold">{value}</span>
      </div>
      <input type="range" min={min} max={max} step={step}
        value={value}
        onChange={e => update(field, parseFloat(e.target.value))}
        aria-label={label}
        className="w-full accent-editorial-brass h-1" />
      <p className="text-eyebrow-sm text-editorial-ivory-mute">{hint}</p>
    </div>
  )
}
