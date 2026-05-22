import { useState, useEffect } from 'react'
import type { Project, AppConfig } from '../types/project'
import { PRODUCTION_PRESETS } from '../lib/guidance'

const API = '/api'

interface Props {
  project: Project
  config: AppConfig | null
  onRefresh: () => void
}

export default function SettingsPanel({ project, config, onRefresh }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [maxTierExpanded, setMaxTierExpanded] = useState(false)
  const [costExpanded, setCostExpanded] = useState(false)
  const [costEstimate, setCostEstimate] = useState<any>(null)
  const [costShotCount, setCostShotCount] = useState(60)
  const [costDialogueRatio, setCostDialogueRatio] = useState(0.5)
  const [audioExpanded, setAudioExpanded] = useState(false)
  const [audioSyncExpanded, setAudioSyncExpanded] = useState(false)
  const [advancedExpanded, setAdvancedExpanded] = useState(false)
  const [postProcExpanded, setPostProcExpanded] = useState(false)
  const [apiEnginesExpanded, setApiEnginesExpanded] = useState(false)
  const [budgetExpanded, setBudgetExpanded] = useState(false)
  const [qualityEngineExpanded, setQualityEngineExpanded] = useState(false)
  const [generatingStyle, setGeneratingStyle] = useState(false)
  const [diskUsage, setDiskUsage] = useState<Record<string, number> | null>(null)
  const [cleaning, setCleaning] = useState(false)
  const s = project.global_settings
  const isMaxTier = ((s as any).quality_tier || 'production') === 'max'

  const update = async (key: string, value: any) => {
    await fetch(`${API}/projects/${project.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ global_settings: { ...s, [key]: value } }),
    })
    onRefresh()
  }

  const applyPreset = async (presetId: string) => {
    const preset = PRODUCTION_PRESETS.find((entry) => entry.id === presetId)
    if (!preset) return
    await fetch(`${API}/projects/${project.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ global_settings: { ...s, ...preset.settings } }),
    })
    onRefresh()
  }

  const generateStyleRules = async () => {
    setGeneratingStyle(true)
    await fetch(`${API}/projects/${project.id}/style-rules`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mood: s.music_mood, color_palette: s.color_palette, music_mood: s.music_mood }),
    })
    setGeneratingStyle(false)
    onRefresh()
  }

  const loadDiskUsage = async () => {
    const res = await fetch(`${API}/projects/${project.id}/disk-usage`)
    if (res.ok) setDiskUsage(await res.json())
  }

  const handleCleanup = async (aggressive = false) => {
    setCleaning(true)
    await fetch(`${API}/projects/${project.id}/cleanup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ aggressive }),
    })
    setCleaning(false)
    loadDiskUsage()
  }

  useEffect(() => { loadDiskUsage() }, [project.id])

  // Live cost estimate — recompute when relevant settings or sliders change
  useEffect(() => {
    if (!costExpanded) return
    const body = {
      shot_count: costShotCount,
      has_dialogue: costDialogueRatio > 0,
      dialogue_shot_ratio: costDialogueRatio,
      quality_tier: isMaxTier ? "max" : "production",
      candidate_count: isMaxTier ? ((s as any).max_candidate_count ?? 8) : 1,
    }
    fetch(`${API}/cost-estimate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(r => r.ok ? r.json() : null)
      .then(setCostEstimate)
      .catch(() => setCostEstimate(null))
  }, [costExpanded, costShotCount, costDialogueRatio, isMaxTier, (s as any).max_candidate_count])

  return (
    <div className="p-4">
      {/* Section: Production Settings */}
      <button onClick={() => setExpanded(!expanded)} className="flex items-center justify-between w-full mb-3">
        <h2 className="text-[11px] font-semibold text-cinema-gold uppercase tracking-widest">Production Settings</h2>
        <span className="text-cinema-muted text-xs">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && (
        <div className="space-y-4">
          <div>
            <div className="mb-1.5 flex items-center justify-between">
              <label className="block text-[10px] uppercase tracking-wider text-cinema-text-secondary">Guided Presets</label>
              <span className="text-[9px] text-cinema-muted">Start from the footage goal, then fine-tune.</span>
            </div>
            <div className="space-y-2">
              {PRODUCTION_PRESETS.map((preset) => (
                <div key={preset.id} className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-xs font-semibold text-cinema-text">{preset.label}</div>
                      <p className="mt-1 text-[10px] leading-relaxed text-cinema-muted">{preset.summary}</p>
                      <p className="mt-1 text-[10px] text-cinema-accent">Use when: {preset.useWhen}</p>
                    </div>
                    <button
                      onClick={() => applyPreset(preset.id)}
                      className="rounded border border-cinema-accent/40 px-2.5 py-1.5 text-[10px] text-cinema-accent hover:bg-cinema-accent/10"
                    >
                      Apply
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Project Language — drives dialogue text, TTS voice selection, transcription */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Dialogue Language</label>
            <select
              value={(s as any).language || 'English'}
              onChange={async e => {
                const newLang = e.target.value
                const currentLang = (s as any).language || 'English'
                // Persist the language change first
                await update('language', newLang)
                // Offer to apply language-optimized defaults
                if (newLang !== currentLang && newLang !== 'English') {
                  const apply = confirm(
                    `Apply ${newLang}-optimized defaults?\n\n` +
                    `This will set the best TTS provider, lipsync engine priority, and validation thresholds for ${newLang} dialogue.\n\n` +
                    `Your custom settings won't be overwritten — only unset fields get defaults.`
                  )
                  if (apply) {
                    const r = await fetch(`${API}/projects/${project.id}/apply-language-defaults`, {
                      method: 'POST',
                      headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ language: newLang, overwrite_existing: false }),
                    })
                    if (r.ok) {
                      const data = await r.json()
                      if (data.changed_fields?.length) {
                        console.log('Applied defaults:', data.changed_fields)
                      }
                      onRefresh()
                    }
                  }
                }
              }}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text">
              <option value="English">English</option>
              <option value="Korean">한국어 (Korean)</option>
              <option value="Japanese">日本語 (Japanese)</option>
              <option value="Mandarin">中文 (Mandarin)</option>
              <option value="Spanish">Español (Spanish)</option>
              <option value="French">Français (French)</option>
              <option value="German">Deutsch (German)</option>
              <option value="Hindi">हिन्दी (Hindi)</option>
              <option value="Arabic">العربية (Arabic)</option>
              <option value="Portuguese">Português (Portuguese)</option>
              <option value="Italian">Italiano (Italian)</option>
              <option value="Russian">Русский (Russian)</option>
            </select>
            <p className="text-[9px] text-cinema-muted mt-0.5">
              Drives dialogue writer output, TTS voice selection, and Whisper/WhisperX transcription language. Image/video prompts stay in English (FLUX/Sora work best in English).
            </p>
            {/* Re-apply defaults button — for users who skipped the confirm or want to refresh */}
            {(s as any).language && (s as any).language !== 'English' && (
              <button
                onClick={async () => {
                  if (!confirm(`Re-apply ${(s as any).language} defaults? This will OVERWRITE any custom TTS/lipsync settings.`)) return
                  const r = await fetch(`${API}/projects/${project.id}/apply-language-defaults`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ language: (s as any).language, overwrite_existing: true }),
                  })
                  if (r.ok) onRefresh()
                }}
                className="mt-1 text-[9px] text-cinema-accent hover:text-cinema-accent2 underline">
                Re-apply {(s as any).language} defaults (overwrite custom settings)
              </button>
            )}
          </div>

          {/* Aspect Ratio */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Aspect Ratio</label>
            <div className="flex gap-1.5">
              {(config?.aspect_ratios || ['16:9', '9:16', '1:1']).map(ar => (
                <button key={ar} onClick={() => update('aspect_ratio', ar)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    s.aspect_ratio === ar
                      ? 'bg-gradient-accent text-white shadow-glow-accent'
                      : 'bg-cinema-bg text-cinema-muted border border-cinema-border-subtle hover:border-cinema-accent/30'
                  }`}>
                  {ar}
                </button>
              ))}
            </div>
          </div>

          {/* Default Video API */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Default Video API</label>
            <select value={s.default_video_api || 'AUTO'} onChange={e => update('default_video_api', e.target.value)}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text">
              {config?.api_registry ? (
                <>
                  {Object.entries(config.api_registry).filter(([, v]) => v.category === 'smart').length > 0 && (
                    <optgroup label="Smart">
                      {Object.entries(config.api_registry).filter(([, v]) => v.category === 'smart').map(([key, info]) => (
                        <option key={key} value={key}>{info.label} — {info.description}</option>
                      ))}
                    </optgroup>
                  )}
                  <optgroup label="Native APIs">
                    {Object.entries(config.api_registry).filter(([, v]) => v.category === 'native').map(([key, info]) => (
                      <option key={key} value={key}>{info.label} — {info.description}</option>
                    ))}
                  </optgroup>
                  <optgroup label="FAL Proxy">
                    {Object.entries(config.api_registry).filter(([, v]) => v.category === 'fal_proxy').map(([key, info]) => (
                      <option key={key} value={key}>{info.label} — {info.description}</option>
                    ))}
                  </optgroup>
                </>
              ) : (
                <>
                  <option value="AUTO">Auto (Smart Routing)</option>
                  <option value="KLING_NATIVE">Kling 3.0 Native</option>
                  <option value="SORA_NATIVE">Sora 2 Native</option>
                  <option value="VEO_NATIVE">Veo 3.1 Native</option>
                </>
              )}
            </select>
            <p className="text-[9px] text-cinema-muted mt-1">Per-shot overrides take precedence. Auto picks best API per shot type.</p>
          </div>

          {config?.workflow_templates && (
            <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[10px] font-mono font-bold uppercase text-cinema-accent">Shot-Type Routing</span>
                <span className="text-[9px] text-cinema-muted">These are the quality defaults the pipeline uses.</span>
              </div>
              <div className="space-y-2">
                {Object.entries(config.workflow_templates).map(([shotType, template]) => (
                  <div key={shotType} className="rounded border border-cinema-border-subtle bg-cinema-panel px-3 py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold capitalize text-cinema-text">{shotType}</span>
                      <span className="rounded bg-cinema-bg px-2 py-0.5 text-[10px] text-cinema-muted">
                        API: {config.api_registry?.[template.target_api]?.label || template.target_api}
                      </span>
                      <span className="rounded bg-cinema-bg px-2 py-0.5 text-[10px] text-cinema-muted">
                        CFG {template.guidance} / {template.steps} steps
                      </span>
                      <span className="rounded bg-cinema-bg px-2 py-0.5 text-[10px] text-cinema-muted">
                        Denoise {template.denoise_default}
                      </span>
                    </div>
                    <p className="mt-1 text-[10px] leading-relaxed text-cinema-muted">{template.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Music Mood — categorized with descriptions */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Music Mood</label>
            <select value={s.music_mood} onChange={e => update('music_mood', e.target.value)}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text">
              <optgroup label="🔪 Tension / Dark">
                <option value="suspense">Suspense — Hans Zimmer tension</option>
                <option value="thriller">Thriller — Trent Reznor chase</option>
                <option value="horror">Horror — Ari Aster dread</option>
                <option value="noir">Noir — smoky jazz detective</option>
                <option value="dystopian">Dystopian — Blade Runner 2049</option>
              </optgroup>
              <optgroup label="💔 Emotional / Dramatic">
                <option value="melancholic">Melancholic — solo piano, Nils Frahm</option>
                <option value="romantic">Romantic — warm guitar, Linklater</option>
                <option value="bittersweet">Bittersweet — violin, Wong Kar-wai</option>
                <option value="grief">Grief — cello, Schindler's List</option>
                <option value="hopeful">Hopeful — rising piano, new beginning</option>
              </optgroup>
              <optgroup label="⚡ Energy / Action">
                <option value="epic">Epic — orchestral, Lord of the Rings</option>
                <option value="action">Action — Bourne Identity intensity</option>
                <option value="triumphant">Triumphant — John Williams glory</option>
                <option value="chase">Chase — relentless hi-hats, tension</option>
              </optgroup>
              <optgroup label="🌊 Ambient / Atmosphere">
                <option value="ethereal">Ethereal — Brian Eno ambient</option>
                <option value="dreamy">Dreamy — lo-fi Tame Impala haze</option>
                <option value="meditative">Meditative — singing bowls, water</option>
                <option value="cosmic">Cosmic — Interstellar organ, vast</option>
              </optgroup>
              <optgroup label="🏙️ Modern / Urban">
                <option value="cyberpunk">Cyberpunk — dark synthwave, neon</option>
                <option value="corporate">Corporate — tech startup, minimal</option>
                <option value="gritty">Gritty — industrial, NIN documentary</option>
                <option value="urban">Urban Lo-Fi — hip hop, coffee shop</option>
                <option value="uplifting">Uplifting — indie, Little Miss Sunshine</option>
              </optgroup>
              <optgroup label="🎭 Period / Genre">
                <option value="jazz_noir">Jazz Noir — Miles Davis, Kind of Blue</option>
                <option value="classical">Classical — Vivaldi string quartet</option>
                <option value="western">Western — Morricone harmonica</option>
                <option value="electronic_minimal">Electronic Minimal — Richie Hawtin</option>
              </optgroup>
            </select>
          </div>

          {/* Color Palette */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Color Palette</label>
            <input type="text" value={s.color_palette || ''} placeholder="e.g., warm amber vs cold blue"
              onChange={e => update('color_palette', e.target.value)}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text placeholder:text-cinema-muted/50" />
          </div>

          {/* Style Rules */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[10px] text-cinema-text-secondary uppercase tracking-wider">AI Style Rules</label>
              <button onClick={generateStyleRules} disabled={generatingStyle}
                className="text-[10px] text-cinema-gold hover:text-cinema-gold-dim font-medium">
                {generatingStyle ? 'Generating...' : s.style_rules && Object.keys(s.style_rules).length ? '↻ Regenerate' : '+ Generate'}
              </button>
            </div>
            {s.style_rules && Object.keys(s.style_rules).length > 0 ? (
              <div className="bg-cinema-bg border border-cinema-border-subtle rounded-lg p-3 space-y-2 max-h-48 overflow-y-auto">
                {Object.entries(s.style_rules).map(([key, val]) => {
                  let display: string
                  if (typeof val === 'string') display = val
                  else if (typeof val === 'object' && val !== null)
                    display = Object.entries(val as Record<string, unknown>).map(([k, v]) => `${k}: ${v}`).join(', ')
                  else display = String(val)
                  return (
                    <div key={key}>
                      <span className="text-[10px] text-cinema-accent font-mono font-bold uppercase">{key.replace(/_/g, ' ')}</span>
                      <p className="text-[10px] text-cinema-muted leading-relaxed mt-0.5">{display.slice(0, 200)}</p>
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="text-[10px] text-cinema-muted italic">Research-enhanced style rules generated from your mood + color palette settings.</p>
            )}
          </div>
        </div>
      )}

      {/* Section: Max Quality Tier */}
      <button onClick={() => setMaxTierExpanded(!maxTierExpanded)} className="flex items-center justify-between w-full mt-5 mb-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-widest flex items-center gap-2">
          <span className={isMaxTier ? 'text-cinema-accent' : 'text-cinema-gold'}>Max Quality Tier</span>
          {isMaxTier && <span className="text-[9px] font-mono bg-cinema-accent/20 text-cinema-accent px-1.5 py-0.5 rounded">ACTIVE</span>}
        </h2>
        <span className="text-cinema-muted text-xs">{maxTierExpanded ? '▾' : '▸'}</span>
      </button>

      {maxTierExpanded && (
        <div className="space-y-4">
          {/* TIER TOGGLE — master switch */}
          <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-3">
            <label className="text-[10px] text-cinema-text-secondary block mb-2 uppercase tracking-wider">Generation Pipeline</label>
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => update('quality_tier', 'production')}
                className={`rounded-lg px-3 py-2.5 text-left transition-all ${
                  !isMaxTier
                    ? 'bg-cinema-gold/10 border border-cinema-gold/40'
                    : 'bg-cinema-panel border border-cinema-border-subtle opacity-60 hover:opacity-100'
                }`}>
                <div className="text-[11px] font-semibold text-cinema-text">Production</div>
                <p className="text-[9px] text-cinema-muted mt-0.5 leading-tight">pulid.json — single-shot, ~30s/shot. Default for throughput.</p>
              </button>
              <button
                onClick={() => update('quality_tier', 'max')}
                className={`rounded-lg px-3 py-2.5 text-left transition-all ${
                  isMaxTier
                    ? 'bg-gradient-accent text-white shadow-glow-accent'
                    : 'bg-cinema-panel border border-cinema-border-subtle opacity-60 hover:opacity-100'
                }`}>
                <div className={`text-[11px] font-semibold ${isMaxTier ? 'text-white' : 'text-cinema-text'}`}>Max Quality</div>
                <p className={`text-[9px] mt-0.5 leading-tight ${isMaxTier ? 'text-white/80' : 'text-cinema-muted'}`}>
                  pulid_max.json — N=8 best-of, ~6 min/shot. Identity ~95%+.
                </p>
              </button>
            </div>
            <p className="text-[9px] text-cinema-muted mt-2">
              Max tier auto-falls-back to production if pulid_max.json or required pod nodes are unavailable.
            </p>
          </div>

          {isMaxTier && (
            <>
              {/* Best-of-N candidate count */}
              <div>
                <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                  <span className="font-mono">Best-of-N candidate budget</span>
                  <span className="text-cinema-accent font-bold">{(s as any).max_candidate_count ?? 8}</span>
                </div>
                <input type="range" min={1} max={16} step={1}
                  value={(s as any).max_candidate_count ?? 8}
                  onChange={e => update('max_candidate_count', parseInt(e.target.value))}
                  className="w-full accent-cinema-accent h-1" />
                <p className="text-[9px] text-cinema-muted">Max candidates per shot. Adaptive halt stops earlier when threshold is met.</p>
              </div>

              {/* Candidate batch size */}
              <div>
                <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                  <span className="font-mono">Candidate batch (halt check interval)</span>
                  <span className="text-cinema-accent font-bold">{(s as any).max_candidate_batch ?? 4}</span>
                </div>
                <input type="range" min={1} max={8} step={1}
                  value={(s as any).max_candidate_batch ?? 4}
                  onChange={e => update('max_candidate_batch', parseInt(e.target.value))}
                  className="w-full accent-cinema-accent h-1" />
                <p className="text-[9px] text-cinema-muted">Generate this many, then score and check halt. Smaller batch = earlier exits possible.</p>
              </div>

              {/* Halt threshold composite */}
              <div>
                <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                  <span className="font-mono">Halt threshold (composite)</span>
                  <span className="text-cinema-accent font-bold">{((s as any).max_halt_threshold_composite ?? 0.92).toFixed(2)}</span>
                </div>
                <input type="range" min={0.70} max={1.00} step={0.01}
                  value={(s as any).max_halt_threshold_composite ?? 0.92}
                  onChange={e => update('max_halt_threshold_composite', parseFloat(e.target.value))}
                  className="w-full accent-cinema-accent h-1" />
                <p className="text-[9px] text-cinema-muted">When best candidate's composite score (0.6 × ArcFace + 0.4 × Aesthetic v2) crosses this, halt early.</p>
              </div>

              {/* Halt min N */}
              <div>
                <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                  <span className="font-mono">Halt minimum N</span>
                  <span className="text-cinema-accent font-bold">{(s as any).max_halt_min_n ?? 4}</span>
                </div>
                <input type="range" min={1} max={8} step={1}
                  value={(s as any).max_halt_min_n ?? 4}
                  onChange={e => update('max_halt_min_n', parseInt(e.target.value))}
                  className="w-full accent-cinema-accent h-1" />
                <p className="text-[9px] text-cinema-muted">Never halt before this many candidates exist, even if threshold met. Guards against single-good-seed luck.</p>
              </div>

              {/* Regenerate floor */}
              <div>
                <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                  <span className="font-mono">Identity regenerate floor (ArcFace)</span>
                  <span className="text-cinema-accent font-bold">{((s as any).max_regenerate_floor_arc ?? 0.82).toFixed(2)}</span>
                </div>
                <input type="range" min={0.50} max={1.00} step={0.01}
                  value={(s as any).max_regenerate_floor_arc ?? 0.82}
                  onChange={e => update('max_regenerate_floor_arc', parseFloat(e.target.value))}
                  className="w-full accent-cinema-accent h-1" />
                <p className="text-[9px] text-cinema-muted">After halt, if best ArcFace is below this, retry once with PuLID weight +0.15. Safety net for identity drift.</p>
              </div>

              {/* Halt rule */}
              <div>
                <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Halt Rule</label>
                <div className="space-y-1">
                  {[
                    { value: 'composite_only', label: 'Composite-only', desc: 'Halt when composite ≥ threshold. Identity folded into composite. Current default.' },
                    { value: 'conjunctive', label: 'Conjunctive (composite AND arc)', desc: 'Halt only when BOTH composite ≥ threshold AND ArcFace ≥ arc threshold.' },
                    { value: 'budget_only', label: 'Budget-only', desc: 'Never halt early. Always run all N candidates, pick best.' },
                  ].map(opt => (
                    <label key={opt.value} className="flex items-start gap-2 rounded-lg border border-cinema-border-subtle bg-cinema-bg px-3 py-2 cursor-pointer hover:border-cinema-accent/30">
                      <input type="radio" name="halt_rule"
                        checked={((s as any).max_halt_rule || 'composite_only') === opt.value}
                        onChange={() => update('max_halt_rule', opt.value)}
                        className="mt-0.5 accent-cinema-accent" />
                      <div>
                        <span className="text-[10px] text-cinema-text font-medium">{opt.label}</span>
                        <p className="text-[9px] text-cinema-muted leading-tight mt-0.5">{opt.desc}</p>
                      </div>
                    </label>
                  ))}
                </div>
              </div>

              {/* Conjunctive: surface the secondary arc threshold */}
              {((s as any).max_halt_rule === 'conjunctive') && (
                <div>
                  <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                    <span className="font-mono">Halt threshold (ArcFace gate)</span>
                    <span className="text-cinema-accent font-bold">{((s as any).max_halt_threshold_arc ?? 0.85).toFixed(2)}</span>
                  </div>
                  <input type="range" min={0.50} max={1.00} step={0.01}
                    value={(s as any).max_halt_threshold_arc ?? 0.85}
                    onChange={e => update('max_halt_threshold_arc', parseFloat(e.target.value))}
                    className="w-full accent-cinema-accent h-1" />
                  <p className="text-[9px] text-cinema-muted">Conjunctive rule only — best candidate's ArcFace must also clear this bar to halt.</p>
                </div>
              )}

              {/* Character LoRA registry */}
              <div>
                <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Per-Character LoRAs</label>
                <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-3 space-y-2">
                  {project.characters.length === 0 ? (
                    <p className="text-[10px] text-cinema-muted italic">No characters in project. Add characters first, then assign a LoRA per character.</p>
                  ) : (
                    project.characters.map((char) => {
                      const loraMap = (s as any).char_lora_paths || {}
                      const loraPath = loraMap[char.id] || ''
                      return (
                        <div key={char.id} className="flex items-center gap-2">
                          <span className="text-[10px] text-cinema-text font-medium w-24 truncate" title={char.name}>{char.name}</span>
                          <input type="text"
                            value={loraPath}
                            placeholder={`loras/${char.id}.safetensors`}
                            onChange={e => update('char_lora_paths', { ...loraMap, [char.id]: e.target.value })}
                            className="flex-1 bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[10px] text-cinema-text font-mono placeholder:text-cinema-muted/50" />
                          {loraPath && (
                            <button
                              onClick={() => {
                                const { [char.id]: _removed, ...rest } = loraMap
                                update('char_lora_paths', rest)
                              }}
                              className="text-[10px] text-cinema-danger hover:text-cinema-danger/80 px-1.5"
                              title="Clear">×</button>
                          )}
                        </div>
                      )
                    })
                  )}
                  <p className="text-[9px] text-cinema-muted mt-1 leading-tight">
                    Train per-character via ai-toolkit/kohya-ss (rank 32, fp16, ~3000 steps). Path is relative to ComfyUI's models/loras/ on the pod.
                  </p>
                </div>
              </div>

              {/* Style reference paths */}
              <div>
                <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">FLUX Redux Style Board</label>
                <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-3 space-y-2">
                  {((s as any).style_reference_paths || []).length === 0 ? (
                    <p className="text-[10px] text-cinema-muted italic">No style references. The face anchor is used as fallback.</p>
                  ) : (
                    ((s as any).style_reference_paths || []).map((path: string, idx: number) => (
                      <div key={idx} className="flex items-center gap-2">
                        <input type="text"
                          value={path}
                          onChange={e => {
                            const arr = [...((s as any).style_reference_paths || [])]
                            arr[idx] = e.target.value
                            update('style_reference_paths', arr)
                          }}
                          className="flex-1 bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[10px] text-cinema-text font-mono" />
                        <button
                          onClick={() => {
                            const arr = ((s as any).style_reference_paths || []).filter((_: any, i: number) => i !== idx)
                            update('style_reference_paths', arr)
                          }}
                          className="text-[10px] text-cinema-danger hover:text-cinema-danger/80 px-1.5">×</button>
                      </div>
                    ))
                  )}
                  <button
                    onClick={() => {
                      const arr = [...((s as any).style_reference_paths || []), '']
                      update('style_reference_paths', arr)
                    }}
                    className="text-[10px] text-cinema-accent hover:text-cinema-accent/80 font-medium">+ Add reference</button>
                  <p className="text-[9px] text-cinema-muted mt-1 leading-tight">
                    8-15 hand-picked images defining cinematography, palette, atmosphere. Averaged via Redux for shot-to-shot style continuity.
                  </p>
                </div>
              </div>

              {/* Cost / time estimate */}
              <div className="rounded-lg border border-cinema-accent/20 bg-cinema-accent/5 p-3">
                <span className="text-[10px] text-cinema-accent font-mono font-bold uppercase">Estimated Cost</span>
                <div className="mt-1.5 grid grid-cols-2 gap-2 text-[10px]">
                  <div>
                    <div className="text-cinema-muted">Per shot (avg)</div>
                    <div className="text-cinema-text font-bold">~{Math.round(((s as any).max_candidate_count ?? 8) * 0.75)} min</div>
                  </div>
                  <div>
                    <div className="text-cinema-muted">60-shot short</div>
                    <div className="text-cinema-text font-bold">~{Math.round(((s as any).max_candidate_count ?? 8) * 0.75 * 60 / 60)} hrs</div>
                  </div>
                </div>
                <p className="text-[9px] text-cinema-muted mt-1.5 leading-tight">
                  Estimates assume RTX 6000 Ada (48GB) at fp16. Adaptive halt typically saves 30-50% on easy shots.
                </p>
              </div>
            </>
          )}
        </div>
      )}

      {/* Section: Cost Estimator (live) */}
      <button onClick={() => setCostExpanded(!costExpanded)} className="flex items-center justify-between w-full mt-5 mb-3">
        <h2 className="text-[11px] font-semibold uppercase tracking-widest flex items-center gap-2">
          <span className="text-cinema-gold">Cost Estimator</span>
          {costEstimate && (
            <span className="text-[9px] font-mono bg-cinema-accent/20 text-cinema-accent px-1.5 py-0.5 rounded">
              ${costEstimate.totals?.grand_total?.toFixed(2)}
            </span>
          )}
        </h2>
        <span className="text-cinema-muted text-xs">{costExpanded ? '▾' : '▸'}</span>
      </button>

      {costExpanded && (
        <div className="space-y-4">
          {/* Sliders */}
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">Shot count</span>
              <span className="text-cinema-accent font-bold">{costShotCount}</span>
            </div>
            <input type="range" min={5} max={120} step={5}
              value={costShotCount}
              onChange={e => setCostShotCount(parseInt(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
          </div>
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">Dialogue shot ratio</span>
              <span className="text-cinema-accent font-bold">{(costDialogueRatio * 100).toFixed(0)}%</span>
            </div>
            <input type="range" min={0} max={1} step={0.05}
              value={costDialogueRatio}
              onChange={e => setCostDialogueRatio(parseFloat(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
            <p className="text-[9px] text-cinema-muted">Fraction of shots with spoken dialogue (drives TTS + lipsync cost).</p>
          </div>

          {/* Breakdown */}
          {costEstimate && (
            <>
              <div className="rounded-lg border border-cinema-accent/20 bg-cinema-accent/5 p-3">
                <div className="text-[10px] text-cinema-muted uppercase tracking-wider mb-1">Total ({costEstimate.quality_tier})</div>
                <div className="text-2xl font-bold text-cinema-accent">${costEstimate.totals?.grand_total?.toFixed(2)}</div>
                <div className="text-[10px] text-cinema-muted mt-0.5">
                  ${costEstimate.per_shot?.avg?.toFixed(3)}/shot avg · {costEstimate.shot_count} shots ({costEstimate.dialogue_shots} dialogue)
                </div>
              </div>

              <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg overflow-hidden">
                <div className="text-[10px] text-cinema-text-secondary uppercase tracking-wider px-3 py-2 border-b border-cinema-border-subtle">By modality</div>
                <table className="w-full text-[10px]">
                  <tbody>
                    {Object.entries(costEstimate.totals).filter(([k]) => k !== "grand_total").map(([k, v]: any) => (
                      <tr key={k} className="border-b border-cinema-border-subtle/30 last:border-0">
                        <td className="px-3 py-1.5 text-cinema-muted font-mono">{k.replace(/_/g, " ")}</td>
                        <td className="px-3 py-1.5 text-right text-cinema-text font-mono">${v.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg overflow-hidden">
                <div className="text-[10px] text-cinema-text-secondary uppercase tracking-wider px-3 py-2 border-b border-cinema-border-subtle">By billing provider</div>
                <table className="w-full text-[10px]">
                  <tbody>
                    {Object.entries(costEstimate.by_provider).map(([k, v]: any) => (
                      <tr key={k} className="border-b border-cinema-border-subtle/30 last:border-0">
                        <td className="px-3 py-1.5 text-cinema-muted font-mono">{k}</td>
                        <td className="px-3 py-1.5 text-right text-cinema-text font-mono">${v.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {costEstimate.notes && costEstimate.notes.length > 0 && (
                <ul className="text-[9px] text-cinema-muted space-y-0.5 list-disc pl-4">
                  {costEstimate.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}
                </ul>
              )}
            </>
          )}
          {!costEstimate && (
            <p className="text-[10px] text-cinema-muted italic">Loading estimate…</p>
          )}
        </div>
      )}

      {/* Section: Budget & Cost */}
      <button onClick={() => setBudgetExpanded(!budgetExpanded)} className="flex items-center justify-between w-full mt-5 mb-3">
        <h2 className="text-[11px] font-semibold text-cinema-gold uppercase tracking-widest">Budget & Cost</h2>
        <span className="text-cinema-muted text-xs">{budgetExpanded ? '▾' : '▸'}</span>
      </button>

      {budgetExpanded && (
        <div className="space-y-4">
          {/* Budget Limit */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Budget Limit (USD)</label>
            <input type="number" min={0} step={1}
              value={(s as any).budget_limit_usd ?? 0}
              onChange={e => update('budget_limit_usd', parseFloat(e.target.value) || 0)}
              placeholder="0 = no limit"
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text font-mono" />
            <p className="text-[9px] text-cinema-muted mt-0.5">Max spend per video. 0 = unlimited. Pipeline pauses when limit reached.</p>
          </div>

          {/* Cost Optimization Level */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Cost Optimization</label>
            <select value={(s as any).cost_optimization || 'quality_first'}
              onChange={e => update('cost_optimization', e.target.value)}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text">
              {(config as any)?.cost_optimization_levels?.map((opt: any) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              )) || (
                <>
                  <option value="quality_first">Quality First</option>
                  <option value="balanced">Balanced</option>
                  <option value="budget_conscious">Budget Conscious</option>
                </>
              )}
            </select>
            <p className="text-[9px] text-cinema-muted mt-0.5">Quality First = best API always. Budget Conscious = cheapest passing API.</p>
          </div>
        </div>
      )}

      {/* Section: Audio & Voice */}
      <button onClick={() => setAudioExpanded(!audioExpanded)} className="flex items-center justify-between w-full mt-5 mb-3">
        <h2 className="text-[11px] font-semibold text-cinema-gold uppercase tracking-widest">Audio & Voice</h2>
        <span className="text-cinema-muted text-xs">{audioExpanded ? '▾' : '▸'}</span>
      </button>

      {audioExpanded && (
        <div className="space-y-4">
          {/* Narration Mode */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Narration Mode</label>
            <select value={(s as any).narration_mode || 'none'} onChange={e => update('narration_mode', e.target.value)}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text">
              <option value="none">No Narration — characters speak their dialogue</option>
              <option value="omniscient">Omniscient Narrator — voiceover above the action</option>
              <option value="character_vo">Character Voiceover — inner monologue</option>
              <option value="documentary">Documentary — neutral informative narrator</option>
            </select>
          </div>

          {/* Narrator Voice (if narration enabled) */}
          {(s as any).narration_mode && (s as any).narration_mode !== 'none' && (
            <div>
              <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Narrator Voice</label>
              <select value={(s as any).narrator_voice || 'auto'} onChange={e => update('narrator_voice', e.target.value)}
                className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text">
                <option value="auto">Auto — matches scene mood</option>
                <option value="Daniel">Daniel — Authoritative British</option>
                <option value="Callum">Callum — Intense, dramatic</option>
                <option value="Adam">Adam — Deep, commanding</option>
                <option value="Patrick">Patrick — Wise, elder</option>
                <option value="Clyde">Clyde — Warm storyteller</option>
                <option value="Charlotte">Charlotte — Warm British woman</option>
                <option value="Rachel">Rachel — Gentle female</option>
              </select>
            </div>
          )}

          {/* Voice Effect */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Voice Effect</label>
            <select value={(s as any).voice_effect || 'none'} onChange={e => update('voice_effect', e.target.value)}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text">
              <optgroup label="Clean">
                <option value="none">None — clean, unprocessed</option>
                <option value="warm_broadcast">Warm Broadcast — polished, compressed</option>
              </optgroup>
              <optgroup label="Cinematic">
                <option value="cinema_reverb">Cinema Reverb — large room echo</option>
                <option value="intimate_room">Intimate Room — small, close</option>
                <option value="cathedral">Cathedral — massive reverb</option>
                <option value="epic_narrator">Epic Narrator — booming, present</option>
                <option value="vintage_film">Vintage Film — old film bandwidth</option>
              </optgroup>
              <optgroup label="Special">
                <option value="telephone">Telephone — bandpass phone call</option>
                <option value="radio">Radio — compressed broadcast</option>
                <option value="megaphone">Megaphone — harsh, distorted</option>
                <option value="underwater">Underwater — muffled, submerged</option>
                <option value="dream_sequence">Dream Sequence — ethereal, slowed</option>
                <option value="robot">Robot — pitch shifted, chorus</option>
                <option value="whisper_intimate">Whisper Enhance — breathy, close</option>
              </optgroup>
            </select>
          </div>

          {/* Music Mastering Preset */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Music Mastering</label>
            <select value={(s as any).music_mastering || 'cinema_master'} onChange={e => update('music_mastering', e.target.value)}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text">
              <option value="none">None — raw, unmastered</option>
              <option value="cinema_master">Cinema Master — warm, wide, polished</option>
              <option value="lo_fi">Lo-Fi — vinyl warmth, tape hiss</option>
              <option value="epic_wide">Epic Wide — orchestral, boosted lows</option>
              <option value="intimate_acoustic">Intimate Acoustic — close, minimal</option>
              <option value="dark_ambient">Dark Ambient — deep, spacious, mysterious</option>
            </select>
          </div>

          {/* Delivery Styles Info */}
          <div className="bg-cinema-bg border border-cinema-border-subtle rounded-lg p-3">
            <span className="text-[10px] text-cinema-accent font-mono font-bold uppercase">40 Voice Delivery Styles</span>
            <p className="text-[10px] text-cinema-muted mt-1 leading-relaxed">
              Set per dialogue line: whisper, angry, crying, scared, sarcastic, commanding, exhausted, drunk, seductive, and 31 more.
              The dialogue writer auto-assigns delivery based on context.
            </p>
          </div>
        </div>
      )}

      {/* Section: Audio & Video Sync */}
      <button onClick={() => setAudioSyncExpanded(!audioSyncExpanded)} className="flex items-center justify-between w-full mt-5 mb-3">
        <h2 className="text-[11px] font-semibold text-cinema-gold uppercase tracking-widest">Audio & Video Sync</h2>
        <span className="text-cinema-muted text-xs">{audioSyncExpanded ? '▾' : '▸'}</span>
      </button>

      {audioSyncExpanded && (
        <div className="space-y-4">
          {/* TTS provider selector — pulled from API_REGISTRY tts modality */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Dialogue TTS Provider</label>
            <select
              value={(s as any).tts_provider || 'ELEVENLABS_V3'}
              onChange={e => update('tts_provider', e.target.value)}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text">
              {config?.api_registry ? (
                <>
                  {(['live', 'beta', 'planned'] as const).map((st) => {
                    const ttsApis = Object.entries(config.api_registry).filter(
                      ([, v]: any) => v.modality === 'tts' && (v.status || 'live') === st
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
            <p className="text-[9px] text-cinema-muted mt-0.5">Active TTS engine for dialogue + narration. Quality / latency / cost shown per option.</p>
          </div>

          {/* Quality enhancer toggles */}
          <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-2 space-y-2">
            <span className="text-[10px] text-cinema-text font-mono uppercase">Dialogue Quality Enhancers</span>
            {[
              { k: 'dialogue_mode_enabled', label: 'ElevenLabs Dialogue Mode', desc: 'Route multi-line dialogue through dedicated endpoint — natural turn-taking + prosody continuity.', def: true },
              { k: 'forced_alignment_enabled', label: 'Forced Alignment (WhisperX)', desc: 'Word-level timestamps + DTW correction. Lipsync accuracy ↑↑.', def: true },
              { k: 'room_tone_matching', label: 'Room Tone Matching', desc: 'Apply scene-environment reverb/EQ to dialogue. Sells the location.', def: false },
              { k: 'prosody_continuity', label: 'Prosody Continuity', desc: 'Smooth pitch/energy across dialogue turns — no abrupt voice resets.', def: true },
            ].map(t => (
              <div key={t.k} className="flex items-start gap-2">
                <input type="checkbox"
                  checked={(s as any)[t.k] !== undefined ? (s as any)[t.k] : t.def}
                  onChange={e => update(t.k, e.target.checked)}
                  className="mt-0.5 accent-cinema-accent" />
                <div>
                  <span className="text-[10px] text-cinema-text font-medium">{t.label}</span>
                  <p className="text-[9px] text-cinema-muted leading-tight">{t.desc}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Lipsync engine priority — ranked list with up/down */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Lipsync Engine Priority</label>
            <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-2 space-y-1">
              {(() => {
                const lipsyncDefault = ['HEDRA_C3', 'SYNC_SO_V3', 'MUSETALK', 'LATENTSYNC', 'OMNIHUMAN_V1_5', 'SYNC_V2']
                const priority: string[] = (s as any).lipsync_engine_priority || lipsyncDefault
                const setPriority = (next: string[]) => update('lipsync_engine_priority', next)
                const move = (idx: number, dir: -1 | 1) => {
                  const j = idx + dir
                  if (j < 0 || j >= priority.length) return
                  const next = [...priority]
                  ;[next[idx], next[j]] = [next[j], next[idx]]
                  setPriority(next)
                }
                return priority.map((key, idx) => {
                  const info = (config?.api_registry as any)?.[key]
                  return (
                    <div key={key} className="flex items-center gap-2 bg-cinema-panel px-2 py-1.5 rounded border border-cinema-border-subtle">
                      <span className="text-[10px] text-cinema-muted font-mono w-5">{idx + 1}.</span>
                      <div className="flex-1">
                        <span className="text-[10px] text-cinema-text font-medium">{info?.label || key}</span>
                        {info && (
                          <span className="ml-1.5 text-[9px] text-cinema-muted">
                            Q{(info.quality_score ?? 0).toFixed(2)} · ${info.per_shot_cost?.toFixed(2)}
                          </span>
                        )}
                      </div>
                      <button onClick={() => move(idx, -1)} disabled={idx === 0}
                        className="text-[10px] text-cinema-muted hover:text-cinema-accent disabled:opacity-30 px-1">↑</button>
                      <button onClick={() => move(idx, 1)} disabled={idx === priority.length - 1}
                        className="text-[10px] text-cinema-muted hover:text-cinema-accent disabled:opacity-30 px-1">↓</button>
                    </div>
                  )
                })
              })()}
              <p className="text-[9px] text-cinema-muted mt-1">Tried in order. First available engine wins. Hedra Character-3 is current SOTA for portrait talking heads.</p>
            </div>
          </div>

          {/* Lipsync validation gate */}
          <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-2 space-y-2">
            <div className="flex items-center gap-2">
              <input type="checkbox"
                checked={(s as any).lipsync_quality_validation !== false}
                onChange={e => update('lipsync_quality_validation', e.target.checked)}
                className="accent-cinema-accent" />
              <div>
                <span className="text-[10px] text-cinema-text font-medium">Lipsync Quality Gate (SyncNet)</span>
                <p className="text-[9px] text-cinema-muted">Score lipsync output via SyncNet. Below threshold → escalate to next engine in priority list.</p>
              </div>
            </div>
            {((s as any).lipsync_quality_validation !== false) && (
              <div>
                <div className="flex justify-between text-[9px] text-cinema-muted mb-0.5">
                  <span className="font-mono">SyncNet confidence threshold</span>
                  <span className="text-cinema-accent font-bold">{((s as any).lipsync_validation_threshold ?? 0.65).toFixed(2)}</span>
                </div>
                <input type="range" min={0.3} max={0.95} step={0.05}
                  value={(s as any).lipsync_validation_threshold ?? 0.65}
                  onChange={e => update('lipsync_validation_threshold', parseFloat(e.target.value))}
                  className="w-full accent-cinema-accent h-1" />
                <p className="text-[9px] text-cinema-muted">0.65 = "convincing in-context"; 0.85+ = "passes close-up scrutiny". Raise for hero shots, lower for B-roll.</p>
              </div>
            )}
          </div>

          {/* Music + foley providers */}
          <div className="grid grid-cols-1 gap-2">
            <div>
              <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Music Provider</label>
              <select value={(s as any).music_provider || 'SUNO_V5'}
                onChange={e => update('music_provider', e.target.value)}
                className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-1.5 text-[10px] text-cinema-text">
                {config?.api_registry && Object.entries(config.api_registry)
                  .filter(([, v]: any) => v.modality === 'music')
                  .map(([k, v]: any) => (
                    <option key={k} value={k} disabled={(v.status || 'live') === 'planned'}>
                      {v.label} {v.status === 'planned' ? '[planned]' : v.status === 'beta' ? '[beta]' : ''}
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Foley / SFX Provider</label>
              <select value={(s as any).foley_provider || 'STABLE_AUDIO_FOLEY'}
                onChange={e => update('foley_provider', e.target.value)}
                className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-1.5 text-[10px] text-cinema-text">
                {config?.api_registry && Object.entries(config.api_registry)
                  .filter(([, v]: any) => v.modality === 'foley')
                  .map(([k, v]: any) => (
                    <option key={k} value={k} disabled={(v.status || 'live') === 'planned'}>
                      {v.label} {v.status === 'planned' ? '[planned]' : v.status === 'beta' ? '[beta]' : ''}
                    </option>
                  ))}
              </select>
            </div>
          </div>

          {/* Purpose-based API matrix */}
          {(config as any)?.purpose_api_ranking && (config as any)?.purpose_tags && (
            <div>
              <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Purpose-Based Routing</label>
              <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg overflow-hidden">
                <table className="w-full text-[10px]">
                  <tbody>
                    {(config as any).purpose_tags.map((purpose: string) => {
                      const ranking: string[] = (config as any).purpose_api_ranking[purpose] || []
                      const override = ((s as any).purpose_overrides || {})[purpose]
                      const liveCandidates = ranking.filter(k => {
                        const info = (config?.api_registry as any)?.[k]
                        return info && (info.status || 'live') !== 'planned'
                      })
                      const chosen = override || liveCandidates[0] || ranking[0]
                      const chosenInfo = (config?.api_registry as any)?.[chosen]
                      return (
                        <tr key={purpose} className="border-b border-cinema-border-subtle/30 last:border-0">
                          <td className="px-2 py-1.5 text-cinema-muted font-mono">{purpose.replace(/_/g, ' ')}</td>
                          <td className="px-2 py-1.5">
                            <select
                              value={chosen}
                              onChange={e => {
                                const next = { ...((s as any).purpose_overrides || {}), [purpose]: e.target.value }
                                if (!e.target.value) delete next[purpose]
                                update('purpose_overrides', next)
                              }}
                              className="w-full bg-cinema-panel border border-cinema-border-subtle rounded px-1.5 py-0.5 text-[10px] text-cinema-text">
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
                          <td className="px-2 py-1.5 text-right text-cinema-muted">
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
              <p className="text-[9px] text-cinema-muted mt-1">Per-purpose API picks. Defaults to the best available (live → beta → planned). Override per purpose to lock in a specific engine.</p>
            </div>
          )}
        </div>
      )}

      {/* Section: Post-Processing */}
      <button onClick={() => setPostProcExpanded(!postProcExpanded)} className="flex items-center justify-between w-full mt-5 mb-3">
        <h2 className="text-[11px] font-semibold text-cinema-gold uppercase tracking-widest">Post-Processing</h2>
        <span className="text-cinema-muted text-xs">{postProcExpanded ? '▾' : '▸'}</span>
      </button>

      {postProcExpanded && (
        <div className="space-y-4">
          {/* Color Grade Preset */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Color Grade</label>
            <select value={(s as any).color_grade_preset || 'warm_cinema'} onChange={e => update('color_grade_preset', e.target.value)}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text">
              <option value="warm_cinema">Warm Cinema — amber highlights, rich shadows</option>
              <option value="cool_noir">Cool Noir — blue shadows, desaturated</option>
              <option value="vibrant">Vibrant — punchy saturation</option>
              <option value="desaturated">Desaturated — muted, washed</option>
              <option value="golden_hour">Golden Hour — warm amber glow</option>
              <option value="moonlight">Moonlight — cool blue, dim</option>
              <option value="high_contrast">High Contrast — crushed blacks, bright highs</option>
              <option value="pastel">Pastel — lifted blacks, soft</option>
            </select>
            <p className="text-[9px] text-cinema-muted mt-0.5">Applied to final assembly. Auto-mapped from mood if not set.</p>
          </div>

          {/* Lip Sync Mode */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Lip Sync Mode</label>
            <select value={(s as any).lip_sync_mode || 'auto'} onChange={e => update('lip_sync_mode', e.target.value)}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text">
              <option value="auto">Auto — AI analyzes shot type + dialogue length</option>
              <option value="overlay">Overlay (MuseTalk) — preserves camera work, replaces mouth only</option>
              <option value="generation">Generation (Omnihuman) — full talking head from still</option>
              <option value="skip">Skip — no lip sync</option>
            </select>
          </div>

          {/* Toggle Row: Face Swap + ReActor */}
          <div className="grid grid-cols-2 gap-2">
            <div className="flex items-center gap-2 bg-cinema-bg rounded-lg px-3 py-2 border border-cinema-border-subtle">
              <input type="checkbox"
                checked={(s as any).face_swap_enabled !== false}
                onChange={e => update('face_swap_enabled', e.target.checked)}
                className="accent-cinema-accent" />
              <div>
                <span className="text-[10px] text-cinema-text font-medium">Face Swap</span>
                <p className="text-[9px] text-cinema-muted">FAL PixVerse post-video</p>
              </div>
            </div>
            <div className="flex items-center gap-2 bg-cinema-bg rounded-lg px-3 py-2 border border-cinema-border-subtle">
              <input type="checkbox"
                checked={(s as any).reactor_enabled !== false}
                onChange={e => update('reactor_enabled', e.target.checked)}
                className="accent-cinema-accent" />
              <div>
                <span className="text-[10px] text-cinema-text font-medium">ReActor</span>
                <p className="text-[9px] text-cinema-muted">ComfyUI face refine</p>
              </div>
            </div>
          </div>

          {/* CodeFormer Fidelity */}
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">CodeFormer fidelity</span>
              <span className="text-cinema-accent font-bold">{(s as any).codeformer_weight ?? 0.7}</span>
            </div>
            <input type="range" min={0} max={1} step={0.1}
              value={(s as any).codeformer_weight ?? 0.7}
              onChange={e => update('codeformer_weight', parseFloat(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
            <p className="text-[9px] text-cinema-muted">0 = max quality (smooth), 1 = max fidelity (sharp). Used by ReActor.</p>
          </div>

          {/* Toggle Row: RIFE + Upscale */}
          <div className="grid grid-cols-2 gap-2">
            <div className="flex items-center gap-2 bg-cinema-bg rounded-lg px-3 py-2 border border-cinema-border-subtle">
              <input type="checkbox"
                checked={(s as any).rife_enabled !== false}
                onChange={e => update('rife_enabled', e.target.checked)}
                className="accent-cinema-accent" />
              <div>
                <span className="text-[10px] text-cinema-text font-medium">RIFE Interpolation</span>
                <p className="text-[9px] text-cinema-muted">30→60fps smoothing</p>
              </div>
            </div>
            <div className="flex items-center gap-2 bg-cinema-bg rounded-lg px-3 py-2 border border-cinema-border-subtle">
              <input type="checkbox"
                checked={(s as any).video_upscale_enabled !== false}
                onChange={e => update('video_upscale_enabled', e.target.checked)}
                className="accent-cinema-accent" />
              <div>
                <span className="text-[10px] text-cinema-text font-medium">SeedVR2 Upscale</span>
                <p className="text-[9px] text-cinema-muted">Cloud video upscale</p>
              </div>
            </div>
          </div>

          {/* Motion Quality Gate */}
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">Motion quality gate</span>
              <span className="text-cinema-accent font-bold">{(s as any).motion_quality_threshold ?? 0.4}</span>
            </div>
            <input type="range" min={0} max={1} step={0.05}
              value={(s as any).motion_quality_threshold ?? 0.4}
              onChange={e => update('motion_quality_threshold', parseFloat(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
            <p className="text-[9px] text-cinema-muted">Min smoothness score to accept video. Below threshold → auto RIFE or regenerate.</p>
          </div>

          {/* Coherence Check Toggle */}
          <div className="flex items-center gap-2 bg-cinema-bg rounded-lg px-3 py-2 border border-cinema-border-subtle">
            <input type="checkbox"
              checked={(s as any).coherence_check_enabled !== false}
              onChange={e => update('coherence_check_enabled', e.target.checked)}
              className="accent-cinema-accent" />
            <div>
              <span className="text-[10px] text-cinema-text font-medium">Coherence Analysis</span>
              <p className="text-[9px] text-cinema-muted">Color/lighting/composition consistency between shots</p>
            </div>
          </div>

          {/* Color Drift Sensitivity */}
          {(s as any).coherence_check_enabled !== false && (
            <div>
              <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                <span className="font-mono">Color drift sensitivity</span>
                <span className="text-cinema-accent font-bold">{(s as any).color_drift_sensitivity ?? 0.3}</span>
              </div>
              <input type="range" min={0.1} max={0.5} step={0.05}
                value={(s as any).color_drift_sensitivity ?? 0.3}
                onChange={e => update('color_drift_sensitivity', parseFloat(e.target.value))}
                className="w-full accent-cinema-accent h-1" />
              <p className="text-[9px] text-cinema-muted">Max color histogram drift before triggering prompt adjustment. Lower = stricter.</p>
            </div>
          )}
        </div>
      )}

      {/* Section: Quality Engine (VBench) */}
      <button onClick={() => setQualityEngineExpanded(!qualityEngineExpanded)} className="flex items-center justify-between w-full mt-5 mb-3">
        <h2 className="text-[11px] font-semibold text-cinema-gold uppercase tracking-widest">Quality Engine</h2>
        <span className="text-cinema-muted text-xs">{qualityEngineExpanded ? '▾' : '▸'}</span>
      </button>

      {qualityEngineExpanded && (
        <div className="space-y-4">
          <p className="text-[9px] text-cinema-muted">VBench-2.0 quality thresholds. Shots scoring below these thresholds trigger regeneration or post-processing fixes.</p>

          {/* VBench Overall Threshold */}
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">VBench acceptance threshold</span>
              <span className="text-cinema-accent font-bold">{(s as any).vbench_overall_threshold ?? 0.60}</span>
            </div>
            <input type="range" min={0} max={1} step={0.05}
              value={(s as any).vbench_overall_threshold ?? 0.60}
              onChange={e => update('vbench_overall_threshold', parseFloat(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
            <p className="text-[9px] text-cinema-muted">Min overall quality score to accept a shot. Below = auto-regenerate.</p>
          </div>

          {/* Identity Strictness */}
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">Identity strictness</span>
              <span className="text-cinema-accent font-bold">{(s as any).identity_strictness ?? 0.60}</span>
            </div>
            <input type="range" min={0} max={1} step={0.05}
              value={(s as any).identity_strictness ?? 0.60}
              onChange={e => update('identity_strictness', parseFloat(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
            <p className="text-[9px] text-cinema-muted">Below this score → recommends face-swap. Higher = stricter face matching.</p>
          </div>

          {/* Temporal Flicker Tolerance */}
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">Temporal flicker tolerance</span>
              <span className="text-cinema-accent font-bold">{(s as any).temporal_flicker_tolerance ?? 0.85}</span>
            </div>
            <input type="range" min={0} max={1} step={0.05}
              value={(s as any).temporal_flicker_tolerance ?? 0.85}
              onChange={e => update('temporal_flicker_tolerance', parseFloat(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
            <p className="text-[9px] text-cinema-muted">Below this → triggers RIFE interpolation. Lower = more permissive.</p>
          </div>

          {/* Regression Sensitivity */}
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">Regression sensitivity</span>
              <span className="text-cinema-accent font-bold">{(s as any).regression_sensitivity ?? 0.05}</span>
            </div>
            <input type="range" min={0.01} max={0.20} step={0.01}
              value={(s as any).regression_sensitivity ?? 0.05}
              onChange={e => update('regression_sensitivity', parseFloat(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
            <p className="text-[9px] text-cinema-muted">Quality drop (%) vs baseline before flagging regression. 0.05 = 5% drop triggers alert.</p>
          </div>
        </div>
      )}

      {/* Section: API Engines */}
      <button onClick={() => setApiEnginesExpanded(!apiEnginesExpanded)} className="flex items-center justify-between w-full mt-5 mb-3">
        <h2 className="text-[11px] font-semibold text-cinema-gold uppercase tracking-widest">API Engines</h2>
        <span className="text-cinema-muted text-xs">{apiEnginesExpanded ? '▾' : '▸'}</span>
      </button>

      {apiEnginesExpanded && (
        <div className="space-y-3">
          <p className="text-[9px] text-cinema-muted mb-2">Enable/disable video APIs and control their per-engine settings. Disabled APIs are skipped in the cascade.</p>

          {/* Cascade Retry Limit */}
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">Cascade retry cycles</span>
              <span className="text-cinema-accent font-bold">{(s as any).cascade_retry_limit ?? 2}</span>
            </div>
            <input type="range" min={0} max={5} step={1}
              value={(s as any).cascade_retry_limit ?? 2}
              onChange={e => update('cascade_retry_limit', parseInt(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
            <p className="text-[9px] text-cinema-muted">Full cascade retries before giving up. 0 = no retries, 2 = default.</p>
          </div>

          {/* API Engine Cards */}
          {[
            { key: 'KLING_NATIVE', label: 'Kling 3.0', icon: '🎯', desc: 'Best faces — subject binding + face lock',
              controls: [
                { field: 'face_consistency', type: 'toggle', label: 'Face Consistency', desc: 'Kling face_consistency flag' },
                { field: 'storyboard_mode', type: 'toggle', label: 'Storyboard Mode', desc: 'Batch 6 shots in unified latent space' },
              ]},
            { key: 'SORA_NATIVE', label: 'Sora 2', icon: '🌊', desc: 'Best motion physics — cloth sim, body momentum',
              controls: [
                { field: 'duration', type: 'select', label: 'Duration', options: ['4', '8', '12', '16', '20'], desc: 'Seconds (strict values only)' },
                { field: 'resolution', type: 'select', label: 'Resolution', options: ['480p', '720p', '1080p'], desc: '' },
              ]},
            { key: 'VEO_NATIVE', label: 'Veo 3.1', icon: '🔮', desc: 'Reference images + native audio + first/last frame',
              controls: [
                { field: 'duration', type: 'select', label: 'Duration', options: ['5s', '6s', '8s'], desc: '' },
                { field: 'generate_audio', type: 'toggle', label: 'Native Audio', desc: 'Generate synced audio with video' },
              ]},
            { key: 'LTX', label: 'LTX 2.3', icon: '💰', desc: '4K support, cheapest, 15 camera motions',
              controls: [
                { field: 'resolution', type: 'select', label: 'Resolution', options: ['480p', '720p', '1080p', '4k'], desc: '' },
                { field: 'camera_motion_native', type: 'toggle', label: 'Native Camera Motion', desc: 'Use LTX 15 camera motion params' },
              ]},
            { key: 'RUNWAY_GEN4', label: 'Runway Gen-4', icon: '🎨', desc: 'Style lock with reference images',
              controls: []},
          ].map(api => {
            const engines = (s as any).api_engines || {}
            const eng = engines[api.key] || config?.api_engine_defaults?.[api.key] || { enabled: true }
            const updateEngine = (field: string, value: any) => {
              const current = (s as any).api_engines || config?.api_engine_defaults || {}
              update('api_engines', { ...current, [api.key]: { ...current[api.key], ...eng, [field]: value } })
            }
            return (
              <div key={api.key} className={`bg-cinema-bg border rounded-lg p-3 transition-all ${
                eng.enabled !== false ? 'border-cinema-accent/30' : 'border-cinema-border-subtle opacity-60'}`}>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">{api.icon}</span>
                    <span className="text-[11px] text-cinema-text font-bold">{api.label}</span>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" checked={eng.enabled !== false}
                      onChange={e => updateEngine('enabled', e.target.checked)}
                      className="sr-only peer" />
                    <div className="w-8 h-4 bg-cinema-border-subtle rounded-full peer peer-checked:bg-cinema-accent
                      after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full
                      after:h-3 after:w-3 after:transition-all peer-checked:after:translate-x-full" />
                  </label>
                </div>
                <p className="text-[9px] text-cinema-muted mb-2">{api.desc}</p>
                {eng.enabled !== false && api.controls.length > 0 && (
                  <div className="space-y-2 pt-2 border-t border-cinema-border-subtle">
                    {api.controls.map((ctrl: any) => (
                      <div key={ctrl.field}>
                        {ctrl.type === 'toggle' ? (
                          <div className="flex items-center gap-2">
                            <input type="checkbox" checked={eng[ctrl.field] !== false}
                              onChange={e => updateEngine(ctrl.field, e.target.checked)}
                              className="accent-cinema-accent" />
                            <span className="text-[10px] text-cinema-text">{ctrl.label}</span>
                            {ctrl.desc && <span className="text-[9px] text-cinema-muted">— {ctrl.desc}</span>}
                          </div>
                        ) : ctrl.type === 'select' ? (
                          <div className="flex items-center gap-2">
                            <span className="text-[10px] text-cinema-muted font-mono w-20">{ctrl.label}</span>
                            <select value={eng[ctrl.field] || ctrl.options[0]}
                              onChange={e => updateEngine(ctrl.field, e.target.value)}
                              className="flex-1 bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[10px] text-cinema-text">
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
        </div>
      )}

      {/* Section: Advanced */}
      <button onClick={() => setAdvancedExpanded(!advancedExpanded)} className="flex items-center justify-between w-full mt-5 mb-3">
        <h2 className="text-[11px] font-semibold text-cinema-gold uppercase tracking-widest">Advanced</h2>
        <span className="text-cinema-muted text-xs">{advancedExpanded ? '▾' : '▸'}</span>
      </button>

      {advancedExpanded && (
        <div className="space-y-4">
          {/* FLUX Guidance Scale */}
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">FLUX guidance scale</span>
              <span className="text-cinema-accent font-bold">{(s as any).flux_guidance ?? 3.5}</span>
            </div>
            <input type="range" min={2.0} max={5.0} step={0.1}
              value={(s as any).flux_guidance ?? 3.5}
              onChange={e => update('flux_guidance', parseFloat(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
            <p className="text-[9px] text-cinema-muted">Prompt adherence. 3.5=FLUX sweet spot. Higher=stricter but risk oversaturation.</p>
          </div>

          {/* Identity Retry Max */}
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">Identity retry max</span>
              <span className="text-cinema-accent font-bold">{(s as any).identity_retry_max ?? 3}</span>
            </div>
            <input type="range" min={1} max={5} step={1}
              value={(s as any).identity_retry_max ?? 3}
              onChange={e => update('identity_retry_max', parseInt(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
            <p className="text-[9px] text-cinema-muted">Max video regeneration attempts when face identity fails.</p>
          </div>

          {/* Coherence Threshold */}
          <div>
            <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
              <span className="font-mono">Coherence threshold</span>
              <span className="text-cinema-accent font-bold">{(s as any).coherence_threshold ?? 0.6}</span>
            </div>
            <input type="range" min={0.3} max={1.0} step={0.05}
              value={(s as any).coherence_threshold ?? 0.6}
              onChange={e => update('coherence_threshold', parseFloat(e.target.value))}
              className="w-full accent-cinema-accent h-1" />
            <p className="text-[9px] text-cinema-muted">Min scene coherence score (color+lighting+composition) to accept. Below = mutation retry.</p>
          </div>

          {/* LLM Preferences */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-2 uppercase tracking-wider">LLM Preferences</label>
            <div className="space-y-3">
              {/* Creative LLM */}
              <div>
                <label className="text-[10px] text-cinema-muted block mb-0.5 font-mono">Creative LLM</label>
                <select value={(s as any).creative_llm || 'auto'}
                  onChange={e => update('creative_llm', e.target.value)}
                  className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-1.5 text-[10px] text-cinema-text">
                  {(config as any)?.creative_llm_options?.map((opt: any) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  )) || (
                    <>
                      <option value="auto">Auto (Router decides)</option>
                      <option value="claude-sonnet">Claude Sonnet 4</option>
                      <option value="gpt-4o">GPT-4o</option>
                    </>
                  )}
                </select>
                <p className="text-[9px] text-cinema-muted">Primary model for scripts, scene descriptions, prompts.</p>
              </div>

              {/* Quality Judge */}
              <div>
                <label className="text-[10px] text-cinema-muted block mb-0.5 font-mono">Quality Judge</label>
                <select value={(s as any).quality_judge_llm || 'auto'}
                  onChange={e => update('quality_judge_llm', e.target.value)}
                  className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-1.5 text-[10px] text-cinema-text">
                  {(config as any)?.quality_judge_options?.map((opt: any) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  )) || (
                    <>
                      <option value="auto">Auto (Best available)</option>
                      <option value="claude-opus">Claude Opus 4</option>
                      <option value="gpt-4o">GPT-4o</option>
                      <option value="gemini-pro">Gemini 2.5 Pro</option>
                    </>
                  )}
                </select>
                <p className="text-[9px] text-cinema-muted">Model for ensemble judging and quality evaluation.</p>
              </div>

              {/* Competitive Generation Toggle */}
              <div className="flex items-center gap-2 bg-cinema-bg rounded-lg px-3 py-2 border border-cinema-border-subtle">
                <input type="checkbox"
                  checked={(s as any).competitive_generation !== false}
                  onChange={e => update('competitive_generation', e.target.checked)}
                  className="accent-cinema-accent" />
                <div>
                  <span className="text-[10px] text-cinema-text font-medium">Competitive Generation</span>
                  <p className="text-[9px] text-cinema-muted">Generate with 2 LLMs, judge picks best. Better quality, 2x LLM cost.</p>
                </div>
              </div>

              {/* Quality vs Cost Weight */}
              <div>
                <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                  <span className="font-mono">Quality ↔ Cost weight</span>
                  <span className="text-cinema-accent font-bold">{(s as any).quality_cost_weight ?? 0.8}</span>
                </div>
                <input type="range" min={0.5} max={1.0} step={0.05}
                  value={(s as any).quality_cost_weight ?? 0.8}
                  onChange={e => update('quality_cost_weight', parseFloat(e.target.value))}
                  className="w-full accent-cinema-accent h-1" />
                <p className="text-[9px] text-cinema-muted">API selection bias. 0.5 = equal weight. 1.0 = quality only. Affects which API is chosen per shot.</p>
              </div>

              {/* Adaptive PuLID Toggle */}
              <div className="flex items-center gap-2 bg-cinema-bg rounded-lg px-3 py-2 border border-cinema-border-subtle">
                <input type="checkbox"
                  checked={(s as any).adaptive_pulid !== false}
                  onChange={e => update('adaptive_pulid', e.target.checked)}
                  className="accent-cinema-accent" />
                <div>
                  <span className="text-[10px] text-cinema-text font-medium">Adaptive PuLID</span>
                  <p className="text-[9px] text-cinema-muted">Auto-adjust face-lock strength based on rolling identity scores.</p>
                </div>
              </div>
            </div>
          </div>

          {/* Master Seed */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-1.5 uppercase tracking-wider">Master Seed</label>
            <input type="number" value={s.master_seed}
              onChange={e => update('master_seed', parseInt(e.target.value))}
              className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-2 text-sm text-cinema-text font-mono" />
            <p className="text-[9px] text-cinema-muted mt-0.5">Locked across all shots for reproducibility</p>
          </div>

          {/* Continuity Parameters */}
          {config?.continuity_options && (
            <div>
              <label className="text-[10px] text-cinema-text-secondary block mb-2 uppercase tracking-wider">Continuity Engine</label>
              <div className="space-y-3">
                {Object.entries(config.continuity_options).map(([key, opt]) => (
                  <div key={key}>
                    <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                      <span className="font-mono">{key.replace(/_/g, ' ')}</span>
                      <span className="text-cinema-accent font-bold">{opt.default}</span>
                    </div>
                    <input type="range" min={opt.min} max={opt.max} step={0.05} defaultValue={opt.default}
                      className="w-full accent-cinema-accent h-1" />
                    <p className="text-[9px] text-cinema-muted">{opt.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ComfyUI Engine Parameters */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-2 uppercase tracking-wider">ComfyUI Engine</label>
            <div className="space-y-3">
              {/* PAG Scale */}
              <div>
                <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                  <span className="font-mono">PAG detail enhancement</span>
                  <span className="text-cinema-accent font-bold">{(s as any).pag_scale ?? 3.0}</span>
                </div>
                <input type="range" min={0} max={5} step={0.5}
                  value={(s as any).pag_scale ?? 3.0}
                  onChange={e => update('pag_scale', parseFloat(e.target.value))}
                  className="w-full accent-cinema-accent h-1" />
                <p className="text-[9px] text-cinema-muted">Sharpens fine detail (skin pores, fabric) without oversaturating. 0=off, 3=default, 5=max</p>
              </div>

              {/* ControlNet Depth Strength */}
              <div>
                <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                  <span className="font-mono">ControlNet depth lock</span>
                  <span className="text-cinema-accent font-bold">{(s as any).controlnet_depth_strength ?? 0.35}</span>
                </div>
                <input type="range" min={0} max={0.8} step={0.05}
                  value={(s as any).controlnet_depth_strength ?? 0.35}
                  onChange={e => update('controlnet_depth_strength', parseFloat(e.target.value))}
                  className="w-full accent-cinema-accent h-1" />
                <p className="text-[9px] text-cinema-muted">Spatial consistency between shots. Higher = stricter layout lock. 0=off</p>
              </div>

              {/* IP-Adapter Style Weight */}
              <div>
                <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                  <span className="font-mono">IP-Adapter style transfer</span>
                  <span className="text-cinema-accent font-bold">{(s as any).ip_adapter_style_weight ?? 0.30}</span>
                </div>
                <input type="range" min={0} max={0.6} step={0.05}
                  value={(s as any).ip_adapter_style_weight ?? 0.30}
                  onChange={e => update('ip_adapter_style_weight', parseFloat(e.target.value))}
                  className="w-full accent-cinema-accent h-1" />
                <p className="text-[9px] text-cinema-muted">Visual style consistency (color grade, atmosphere) from previous shot. 0=off</p>
              </div>

              {/* Upscale Toggle */}
              <div className="flex items-center gap-2 bg-cinema-bg rounded-lg px-3 py-2 border border-cinema-border-subtle">
                <input type="checkbox"
                  checked={(s as any).comfyui_upscale !== false}
                  onChange={e => update('comfyui_upscale', e.target.checked)}
                  className="accent-cinema-accent" />
                <div>
                  <span className="text-[10px] text-cinema-text font-medium">On-GPU 4x Upscale (Real-ESRGAN)</span>
                  <p className="text-[9px] text-cinema-muted">Upscale on RunPod GPU instead of FAL API. Output: 2688x1536</p>
                </div>
              </div>

              {/* Sampler Selection (production + max share this) */}
              <div>
                <label className="text-[10px] text-cinema-muted block mb-0.5 font-mono">Sampler</label>
                <select value={(s as any).comfyui_sampler || (isMaxTier ? 'dpmpp_3m_sde_gpu' : 'dpmpp_2m')}
                  onChange={e => update('comfyui_sampler', e.target.value)}
                  className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-1.5 text-[10px] text-cinema-text">
                  <option value="dpmpp_2m">DPM++ 2M (production default)</option>
                  <option value="euler">Euler (fast, lower quality)</option>
                  <option value="dpmpp_2m_sde">DPM++ 2M SDE (stochastic, creative)</option>
                  <option value="dpmpp_3m_sde">DPM++ 3M SDE (CPU)</option>
                  <option value="dpmpp_3m_sde_gpu">DPM++ 3M SDE GPU (max-tier default, sharpest)</option>
                  <option value="uni_pc">UniPC (fast convergence)</option>
                </select>
              </div>

              {/* Steps — production tier control */}
              {!isMaxTier && (
                <div>
                  <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                    <span className="font-mono">Sampling steps</span>
                    <span className="text-cinema-accent font-bold">{(s as any).comfyui_steps ?? 20}</span>
                  </div>
                  <input type="range" min={10} max={40} step={1}
                    value={(s as any).comfyui_steps ?? 20}
                    onChange={e => update('comfyui_steps', parseInt(e.target.value))}
                    className="w-full accent-cinema-accent h-1" />
                  <p className="text-[9px] text-cinema-muted">Higher = more detail but slower. 20 is balanced, 25+ for portraits.</p>
                </div>
              )}

              {/* ---------- MAX-TIER ONLY CONTROLS ---------- */}
              {isMaxTier && (
                <>
                  <div className="rounded-lg border border-cinema-accent/20 bg-cinema-accent/5 px-3 py-2 mt-2">
                    <span className="text-[10px] text-cinema-accent font-mono font-bold uppercase">Max-tier engine</span>
                    <p className="text-[9px] text-cinema-muted mt-0.5">Controls below only apply when Quality Tier = Max.</p>
                  </div>

                  {/* AYS steps */}
                  <div>
                    <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                      <span className="font-mono">AYS scheduler steps</span>
                      <span className="text-cinema-accent font-bold">{(s as any).ays_steps ?? 28}</span>
                    </div>
                    <input type="range" min={15} max={40} step={1}
                      value={(s as any).ays_steps ?? 28}
                      onChange={e => update('ays_steps', parseInt(e.target.value))}
                      className="w-full accent-cinema-accent h-1" />
                    <p className="text-[9px] text-cinema-muted">Align Your Steps — NVIDIA-optimal sigma schedule for FLUX. 28 is the sweet spot.</p>
                  </div>

                  {/* SLG scale */}
                  <div>
                    <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                      <span className="font-mono">SLG (Skip Layer Guidance)</span>
                      <span className="text-cinema-accent font-bold">{((s as any).slg_scale ?? 2.5).toFixed(1)}</span>
                    </div>
                    <input type="range" min={0} max={5} step={0.1}
                      value={(s as any).slg_scale ?? 2.5}
                      onChange={e => update('slg_scale', parseFloat(e.target.value))}
                      className="w-full accent-cinema-accent h-1" />
                    <p className="text-[9px] text-cinema-muted">Skip-layer guidance on DiT layers 7-11. Single biggest realism toggle on FLUX. 0 = off.</p>
                  </div>

                  {/* DetailDaemon amount */}
                  <div>
                    <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                      <span className="font-mono">DetailDaemon amount</span>
                      <span className="text-cinema-accent font-bold">{((s as any).detail_daemon_amount ?? 0.5).toFixed(2)}</span>
                    </div>
                    <input type="range" min={0} max={1} step={0.05}
                      value={(s as any).detail_daemon_amount ?? 0.5}
                      onChange={e => update('detail_daemon_amount', parseFloat(e.target.value))}
                      className="w-full accent-cinema-accent h-1" />
                    <p className="text-[9px] text-cinema-muted">Mid-sampling sigma injection. Adds micro-texture (skin pores, fabric weave). 0 = off.</p>
                  </div>

                  {/* FreeU v2 — uses FLUX-compatible build in max stack */}
                  <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-2 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-cinema-text font-mono">FreeU v2 (skip-connection amplify)</span>
                      <span className="text-[9px] text-cinema-muted">FLUX-compatible build required on pod</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { k: 'freeu_b1', label: 'b1 (backbone 1)', def: 1.3, min: 1.0, max: 1.8 },
                        { k: 'freeu_b2', label: 'b2 (backbone 2)', def: 1.4, min: 1.0, max: 1.8 },
                        { k: 'freeu_s1', label: 's1 (skip 1)', def: 0.9, min: 0.0, max: 1.5 },
                        { k: 'freeu_s2', label: 's2 (skip 2)', def: 0.2, min: 0.0, max: 1.5 },
                      ].map((f) => (
                        <div key={f.k}>
                          <div className="flex justify-between text-[9px] text-cinema-muted mb-0.5">
                            <span className="font-mono">{f.label}</span>
                            <span className="text-cinema-accent font-bold">{(((s as any)[f.k] ?? f.def) as number).toFixed(2)}</span>
                          </div>
                          <input type="range" min={f.min} max={f.max} step={0.05}
                            value={(s as any)[f.k] ?? f.def}
                            onChange={e => update(f.k, parseFloat(e.target.value))}
                            className="w-full accent-cinema-accent h-1" />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* 4-channel Union ControlNet */}
                  <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-2 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-cinema-text font-mono">FLUX Union CN Pro — 4 channels</span>
                      <span className="text-[9px] text-cinema-muted">total budget &lt; 1.2</span>
                    </div>
                    {[
                      { k: 'controlnet_depth_strength', label: 'Depth (spatial anchor)', def: 0.40, max: 0.8 },
                      { k: 'controlnet_canny_strength', label: 'Canny (edge coherence)', def: 0.15, max: 0.5 },
                      { k: 'controlnet_pose_strength', label: 'Pose (DWPose, body+hand+face)', def: 0.35, max: 0.6 },
                      { k: 'controlnet_tile_strength', label: 'Tile (texture preservation)', def: 0.25, max: 0.5 },
                    ].map((c) => {
                      const v = (s as any)[c.k] ?? c.def
                      return (
                        <div key={c.k}>
                          <div className="flex justify-between text-[9px] text-cinema-muted mb-0.5">
                            <span className="font-mono">{c.label}</span>
                            <span className="text-cinema-accent font-bold">{(v as number).toFixed(2)}</span>
                          </div>
                          <input type="range" min={0} max={c.max} step={0.05}
                            value={v}
                            onChange={e => update(c.k, parseFloat(e.target.value))}
                            className="w-full accent-cinema-accent h-1" />
                        </div>
                      )
                    })}
                  </div>

                  {/* Redux strength */}
                  <div>
                    <label className="text-[10px] text-cinema-muted block mb-0.5 font-mono">FLUX Redux style strength</label>
                    <select value={(s as any).redux_strength || 'high'}
                      onChange={e => update('redux_strength', e.target.value)}
                      className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-1.5 text-[10px] text-cinema-text">
                      <option value="high">High — strong style lock from board</option>
                      <option value="medium">Medium — balanced</option>
                      <option value="low">Low — subtle influence</option>
                    </select>
                    <p className="text-[9px] text-cinema-muted mt-0.5">FLUX-native image conditioning. Replaces SDXL-era IP-Adapter on FLUX.</p>
                  </div>

                  {/* Hires fix toggle + denoise */}
                  <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-2 space-y-2">
                    <div className="flex items-center gap-2">
                      <input type="checkbox"
                        checked={(s as any).hires_fix_enabled !== false}
                        onChange={e => update('hires_fix_enabled', e.target.checked)}
                        className="accent-cinema-accent" />
                      <div>
                        <span className="text-[10px] text-cinema-text font-medium">Hires-fix (Pass 2)</span>
                        <p className="text-[9px] text-cinema-muted">1.5× latent upscale + 2nd denoise pass. Adds detail ESRGAN can't fabricate.</p>
                      </div>
                    </div>
                    {((s as any).hires_fix_enabled !== false) && (
                      <div>
                        <div className="flex justify-between text-[9px] text-cinema-muted mb-0.5">
                          <span className="font-mono">Pass 2 denoise</span>
                          <span className="text-cinema-accent font-bold">{((s as any).hires_fix_denoise ?? 0.40).toFixed(2)}</span>
                        </div>
                        <input type="range" min={0.2} max={0.6} step={0.05}
                          value={(s as any).hires_fix_denoise ?? 0.40}
                          onChange={e => update('hires_fix_denoise', parseFloat(e.target.value))}
                          className="w-full accent-cinema-accent h-1" />
                      </div>
                    )}
                  </div>

                  {/* FaceDetailer */}
                  <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-2 space-y-2">
                    <div className="flex items-center gap-2">
                      <input type="checkbox"
                        checked={(s as any).face_detailer_enabled !== false}
                        onChange={e => update('face_detailer_enabled', e.target.checked)}
                        className="accent-cinema-accent" />
                      <div>
                        <span className="text-[10px] text-cinema-text font-medium">FaceDetailer (Impact Pack)</span>
                        <p className="text-[9px] text-cinema-muted">Auto-detect face → re-denoise at guide size. Recognizable → convincing.</p>
                      </div>
                    </div>
                    {((s as any).face_detailer_enabled !== false) && (
                      <div>
                        <label className="text-[9px] text-cinema-muted block mb-0.5 font-mono">Guide size</label>
                        <select value={(s as any).face_detailer_guide_size ?? 1024}
                          onChange={e => update('face_detailer_guide_size', parseInt(e.target.value))}
                          className="w-full bg-cinema-panel border border-cinema-border-subtle rounded px-2 py-1 text-[10px] text-cinema-text">
                          <option value={512}>512 — fast</option>
                          <option value={1024}>1024 — recommended</option>
                          <option value={2048}>2048 — slow, max detail</option>
                        </select>
                      </div>
                    )}
                  </div>

                  {/* SUPIR upscale */}
                  <div className="rounded-lg border border-cinema-border-subtle bg-cinema-bg p-2 space-y-2">
                    <div className="flex items-center gap-2">
                      <input type="checkbox"
                        checked={(s as any).supir_enabled !== false}
                        onChange={e => update('supir_enabled', e.target.checked)}
                        className="accent-cinema-accent" />
                      <div>
                        <span className="text-[10px] text-cinema-text font-medium">SUPIR 4× upscale (replaces Real-ESRGAN)</span>
                        <p className="text-[9px] text-cinema-muted">Photorealism-tuned restoration. 5-10× better than ESRGAN on faces. Adds ~35s/shot.</p>
                      </div>
                    </div>
                    {((s as any).supir_enabled !== false) && (
                      <div>
                        <div className="flex justify-between text-[9px] text-cinema-muted mb-0.5">
                          <span className="font-mono">SUPIR steps</span>
                          <span className="text-cinema-accent font-bold">{(s as any).supir_steps ?? 50}</span>
                        </div>
                        <input type="range" min={20} max={100} step={5}
                          value={(s as any).supir_steps ?? 50}
                          onChange={e => update('supir_steps', parseInt(e.target.value))}
                          className="w-full accent-cinema-accent h-1" />
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Post-Processing Pipeline */}
          {config?.post_processing && (
            <div>
              <label className="text-[10px] text-cinema-text-secondary block mb-2 uppercase tracking-wider">Post-Processing</label>
              <div className="space-y-1">
                {Object.entries(config.post_processing).map(([key, val]) => (
                  <div key={key} className="flex items-center gap-2 bg-cinema-bg rounded-lg px-3 py-2 border border-cinema-border-subtle">
                    <div className={`w-2 h-2 rounded-full ${val.available ? 'bg-cinema-success' : 'bg-cinema-muted'}`} />
                    <span className="text-[10px] text-cinema-text font-medium">{key.replace(/_/g, ' ')}</span>
                    <span className="text-[9px] text-cinema-muted flex-1 text-right">{val.description}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Disk Usage + Cleanup */}
          <div>
            <label className="text-[10px] text-cinema-text-secondary block mb-2 uppercase tracking-wider">Storage</label>
            {diskUsage && (
              <div className="bg-cinema-bg border border-cinema-border-subtle rounded-lg p-3 space-y-1.5">
                {Object.entries(diskUsage).filter(([k]) => k !== 'total').map(([k, v]) => (
                  <div key={k} className="flex justify-between text-[10px]">
                    <span className="text-cinema-muted font-mono">{k}/</span>
                    <span className="text-cinema-text">{v} MB</span>
                  </div>
                ))}
                <div className="flex justify-between text-[10px] border-t border-cinema-border-subtle pt-1 mt-1">
                  <span className="text-cinema-text font-bold">Total</span>
                  <span className="text-cinema-gold font-bold">{diskUsage.total} MB</span>
                </div>
              </div>
            )}
            <div className="flex gap-2 mt-2">
              <button onClick={() => handleCleanup(false)} disabled={cleaning}
                className="text-[10px] px-3 py-1.5 rounded-lg border border-cinema-border-subtle text-cinema-muted hover:text-cinema-text hover:border-cinema-accent/30 flex-1">
                {cleaning ? 'Cleaning...' : 'Clean Temp Files'}
              </button>
              <button onClick={() => handleCleanup(true)} disabled={cleaning}
                className="text-[10px] px-3 py-1.5 rounded-lg border border-cinema-danger/30 text-cinema-danger hover:bg-cinema-danger/10 flex-1">
                Deep Clean
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
