import { useState, useEffect } from 'react'
import type { Project, AppConfig } from '../types/project'

const API = '/api'

interface Props {
  project: Project
  config: AppConfig | null
  onRefresh: () => void
}

export default function SettingsPanel({ project, config, onRefresh }: Props) {
  const [expanded, setExpanded] = useState(true)
  const [audioExpanded, setAudioExpanded] = useState(false)
  const [advancedExpanded, setAdvancedExpanded] = useState(false)
  const [postProcExpanded, setPostProcExpanded] = useState(false)
  const [apiEnginesExpanded, setApiEnginesExpanded] = useState(false)
  const [budgetExpanded, setBudgetExpanded] = useState(false)
  const [qualityEngineExpanded, setQualityEngineExpanded] = useState(false)
  const [generatingStyle, setGeneratingStyle] = useState(false)
  const [diskUsage, setDiskUsage] = useState<Record<string, number> | null>(null)
  const [cleaning, setCleaning] = useState(false)
  const s = project.global_settings

  const update = async (key: string, value: any) => {
    await fetch(`${API}/projects/${project.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ global_settings: { ...s, [key]: value } }),
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

  return (
    <div className="p-4">
      {/* Section: Production Settings */}
      <button onClick={() => setExpanded(!expanded)} className="flex items-center justify-between w-full mb-3">
        <h2 className="text-[11px] font-semibold text-cinema-gold uppercase tracking-widest">Production Settings</h2>
        <span className="text-cinema-muted text-xs">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && (
        <div className="space-y-4">
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

              {/* FreeU Note */}
              <div className="flex items-center gap-2 bg-cinema-bg rounded-lg px-3 py-2 border border-cinema-border-subtle opacity-50">
                <div className="w-2 h-2 rounded-full bg-cinema-muted" />
                <div>
                  <span className="text-[10px] text-cinema-muted font-medium">FreeU V2 — Not compatible with FLUX</span>
                  <p className="text-[9px] text-cinema-muted">FreeU requires SD1.5/SDXL UNet architecture. PAG provides similar benefits for FLUX.</p>
                </div>
              </div>

              {/* Sampler Selection */}
              <div>
                <label className="text-[10px] text-cinema-muted block mb-0.5 font-mono">Sampler</label>
                <select value={(s as any).comfyui_sampler || 'dpmpp_2m'}
                  onChange={e => update('comfyui_sampler', e.target.value)}
                  className="w-full bg-cinema-bg border border-cinema-border-subtle rounded-lg px-3 py-1.5 text-[10px] text-cinema-text">
                  <option value="dpmpp_2m">DPM++ 2M (recommended)</option>
                  <option value="euler">Euler (fast, lower quality)</option>
                  <option value="dpmpp_2m_sde">DPM++ 2M SDE (stochastic, creative)</option>
                  <option value="dpmpp_3m_sde">DPM++ 3M SDE (highest quality, slow)</option>
                  <option value="uni_pc">UniPC (fast convergence)</option>
                </select>
              </div>

              {/* Steps */}
              <div>
                <div className="flex justify-between text-[10px] text-cinema-muted mb-0.5">
                  <span className="font-mono">Sampling steps</span>
                  <span className="text-cinema-accent font-bold">{(s as any).comfyui_steps ?? 20}</span>
                </div>
                <input type="range" min={10} max={40} step={1}
                  value={(s as any).comfyui_steps ?? 20}
                  onChange={e => update('comfyui_steps', parseInt(e.target.value))}
                  className="w-full accent-cinema-accent h-1" />
                <p className="text-[9px] text-cinema-muted">Higher = more detail but slower. 20 is balanced, 25+ for portraits</p>
              </div>
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
