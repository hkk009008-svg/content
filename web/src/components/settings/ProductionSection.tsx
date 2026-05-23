import { useState } from 'react'
import type { Project, AppConfig } from '../../types/project'
import { PRODUCTION_PRESETS } from '../../lib/guidance'
import { SettingsSection } from './SettingsSection'
import { INPUT_CLS, LABEL_CLS, HINT_CLS, CARD_CLS } from './styles'

const API = '/api'

interface Props {
  s: any
  config: AppConfig | null
  project: Project
  update: (key: string, value: any) => void | Promise<void>
  onRefresh: () => void
}

export function ProductionSection({ s, config, project, update, onRefresh }: Props) {
  const [generatingStyle, setGeneratingStyle] = useState(false)

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
      body: JSON.stringify({
        mood: s.music_mood,
        color_palette: s.color_palette,
        music_mood: s.music_mood,
      }),
    })
    setGeneratingStyle(false)
    onRefresh()
  }

  const handleLanguageChange = async (newLang: string) => {
    const currentLang = s.language || 'English'
    await update('language', newLang)
    if (newLang !== currentLang && newLang !== 'English') {
      const apply = confirm(
        `Apply ${newLang}-optimized defaults?\n\n` +
        `This will set the best TTS provider, lipsync engine priority, and validation thresholds for ${newLang} dialogue.\n\n` +
        `Your custom settings won't be overwritten — only unset fields get defaults.`,
      )
      if (apply) {
        const r = await fetch(`${API}/projects/${project.id}/apply-language-defaults`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ language: newLang, overwrite_existing: false }),
        })
        if (r.ok) onRefresh()
      }
    }
  }

  const reapplyLanguageDefaults = async () => {
    if (!confirm(`Re-apply ${s.language} defaults? This will OVERWRITE any custom TTS/lipsync settings.`)) return
    const r = await fetch(`${API}/projects/${project.id}/apply-language-defaults`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language: s.language, overwrite_existing: true }),
    })
    if (r.ok) onRefresh()
  }

  return (
    <SettingsSection title="Production Settings" defaultExpanded>
      {/* Guided Presets */}
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <label className={LABEL_CLS}>Guided Presets</label>
          <span className="text-eyebrow-sm text-editorial-ivory-mute">
            Start from the footage goal, then fine-tune.
          </span>
        </div>
        <div className="space-y-2">
          {PRODUCTION_PRESETS.map((preset) => (
            <div key={preset.id} className={CARD_CLS}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs font-semibold text-editorial-ivory">{preset.label}</div>
                  <p className="mt-1 text-eyebrow leading-relaxed text-editorial-ivory-mute">{preset.summary}</p>
                  <p className="mt-1 text-eyebrow text-editorial-brass">Use when: {preset.useWhen}</p>
                </div>
                <button
                  type="button"
                  onClick={() => applyPreset(preset.id)}
                  className="rounded border border-editorial-brass/40 px-2.5 py-1.5 text-eyebrow text-editorial-brass hover:bg-editorial-brass/10"
                >
                  Apply
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Dialogue Language */}
      <div>
        <label className={LABEL_CLS}>Dialogue Language</label>
        <select
          value={s.language || 'English'}
          onChange={(e) => handleLanguageChange(e.target.value)}
          className={INPUT_CLS}
        >
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
        <p className={HINT_CLS}>
          Drives dialogue writer output, TTS voice selection, and Whisper/WhisperX transcription language.
          Image/video prompts stay in English (FLUX/Sora work best in English).
        </p>
        {s.language && s.language !== 'English' && (
          <button
            type="button"
            onClick={reapplyLanguageDefaults}
            className="mt-1 text-eyebrow-sm text-editorial-brass hover:text-editorial-brass-deep underline"
          >
            Re-apply {s.language} defaults (overwrite custom settings)
          </button>
        )}
      </div>

      {/* Aspect Ratio */}
      <div>
        <label className={LABEL_CLS}>Aspect Ratio</label>
        <div className="flex gap-1.5">
          {(config?.aspect_ratios || ['16:9', '9:16', '1:1']).map((ar) => (
            <button
              key={ar}
              type="button"
              onClick={() => update('aspect_ratio', ar)}
              aria-pressed={s.aspect_ratio === ar}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                s.aspect_ratio === ar
                  ? 'bg-gradient-accent text-editorial-ink shadow-glow-accent'
                  : 'bg-editorial-ink text-editorial-ivory-mute border border-editorial-rule hover:border-editorial-brass/30'
              }`}
            >
              {ar}
            </button>
          ))}
        </div>
      </div>

      {/* Workflow Templates info */}
      {config?.workflow_templates && (
        <div className={CARD_CLS}>
          <div className="mb-2 flex items-center justify-between">
            <span className="text-eyebrow font-mono font-bold uppercase text-editorial-brass">Shot-Type Routing</span>
            <span className="text-eyebrow-sm text-editorial-ivory-mute">These are the quality defaults the pipeline uses.</span>
          </div>
          <div className="space-y-2">
            {Object.entries(config.workflow_templates).map(([shotType, template]) => (
              <div key={shotType} className="rounded border border-editorial-rule bg-editorial-ink-soft px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold capitalize text-editorial-ivory">{shotType}</span>
                  <span className="rounded bg-editorial-ink px-2 py-0.5 text-eyebrow text-editorial-ivory-mute">
                    API: {config.api_registry?.[template.target_api]?.label || template.target_api}
                  </span>
                  <span className="rounded bg-editorial-ink px-2 py-0.5 text-eyebrow text-editorial-ivory-mute">
                    CFG {template.guidance} / {template.steps} steps
                  </span>
                  <span className="rounded bg-editorial-ink px-2 py-0.5 text-eyebrow text-editorial-ivory-mute">
                    Denoise {template.denoise_default}
                  </span>
                </div>
                <p className="mt-1 text-eyebrow leading-relaxed text-editorial-ivory-mute">{template.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Music Mood */}
      <div>
        <label className={LABEL_CLS}>Music Mood</label>
        <select
          value={s.music_mood}
          onChange={(e) => update('music_mood', e.target.value)}
          className={INPUT_CLS}
        >
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
        <label className={LABEL_CLS}>Color Palette</label>
        <input
          type="text"
          value={s.color_palette || ''}
          placeholder="e.g., warm amber vs cold blue"
          onChange={(e) => update('color_palette', e.target.value)}
          className={`${INPUT_CLS} placeholder:text-editorial-ivory-mute/50`}
        />
      </div>

      {/* AI Style Rules */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className={LABEL_CLS.replace('block ', '')}>AI Style Rules</label>
          <button
            type="button"
            onClick={generateStyleRules}
            disabled={generatingStyle}
            className="text-eyebrow text-editorial-brass hover:text-editorial-brass-deep font-medium disabled:opacity-50"
          >
            {generatingStyle
              ? 'Generating...'
              : s.style_rules && Object.keys(s.style_rules).length
              ? '↻ Regenerate'
              : '+ Generate'}
          </button>
        </div>
        {s.style_rules && Object.keys(s.style_rules).length > 0 ? (
          <div className={`${CARD_CLS} space-y-2 max-h-48 overflow-y-auto`}>
            {Object.entries(s.style_rules).map(([key, val]) => {
              let display: string
              if (typeof val === 'string') display = val
              else if (typeof val === 'object' && val !== null)
                display = Object.entries(val as Record<string, unknown>)
                  .map(([k, v]) => `${k}: ${v}`)
                  .join(', ')
              else display = String(val)
              return (
                <div key={key}>
                  <span className="text-eyebrow text-editorial-brass font-mono font-bold uppercase">
                    {key.replace(/_/g, ' ')}
                  </span>
                  <p className="text-eyebrow text-editorial-ivory-mute leading-relaxed mt-0.5">
                    {display.slice(0, 200)}
                  </p>
                </div>
              )
            })}
          </div>
        ) : (
          <p className="text-eyebrow text-editorial-ivory-mute italic">
            Research-enhanced style rules generated from your mood + color palette settings.
          </p>
        )}
      </div>
    </SettingsSection>
  )
}
