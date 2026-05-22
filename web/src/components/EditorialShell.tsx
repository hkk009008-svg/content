/**
 * EditorialShell — the cinema-editorial wrapper for setup mode.
 *
 * Aesthetic: dark paper-black canvas with warm ivory typography in
 * Fraunces (variable serif, opsz=144 for display). Single arterial
 * red accent (curtain), single warm brass highlight (lamp).
 *
 * Composition:
 *   ┌─────────────────────────────────────────────────────────────┐
 *   │  NOW SHOWING marquee (only while generating)                │
 *   ├──────────────────────────────────┬──────────────────────────┤
 *   │  Reel № / Project name (display)│  Vertical metadata column│
 *   │                                  │  (act / runtime / status)│
 *   ├──────────────────────────────────┴──────────────────────────┤
 *   │  Editorial figures: 03 scenes · 27 shots · 05 characters    │
 *   ├─────────────────────────────────────────────────────────────┤
 *   │  Scene cue sheet                                            │
 *   ├─────────────────────────────────────────────────────────────┤
 *   │  [ Existing 3-col panel grid ] — kept intact                │
 *   └─────────────────────────────────────────────────────────────┘
 */
import { useMemo } from 'react'
import type { Project, AppConfig, ProgressEvent } from '../types/project'
import CharacterPanel from './CharacterPanel'
import LocationPanel from './LocationPanel'
import ObjectPanel from './ObjectPanel'
import ScenePanel from './ScenePanel'
import SettingsPanel from './SettingsPanel'
import GenerationPanel from './GenerationPanel'
import PreviewPanel from './PreviewPanel'

interface EditorialShellProps {
  project: Project
  config: AppConfig | null
  events: ProgressEvent[]
  latest: ProgressEvent | null
  isStreaming: boolean
  generating: boolean
  onBackToProjects: () => void
  onGenerate: () => void
  onCancel: () => void
  onRefreshProject: () => Promise<void> | void
  apiBase: string
}

/* ─── Helpers ─────────────────────────────────────────────────── */

const pad2 = (n: number) => n.toString().padStart(2, '0')

const formatRuntime = (seconds: number): string => {
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}:${pad2(s)}`
}

/* ─── Sub-components ──────────────────────────────────────────── */

/** Eyebrow — small, wide-tracked, mono. Used above big serif moments. */
function Eyebrow({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={`font-mono text-[10px] text-editorial-ivory-mute tracking-wide-eyebrow uppercase ${className}`}
    >
      {children}
    </div>
  )
}

/** Big editorial figure — a Fraunces numeral with a thin label beneath. */
function Figure({
  value,
  label,
  delay = 0,
}: {
  value: number | string
  label: string
  delay?: number
}) {
  return (
    <div
      className="flex flex-col items-baseline gap-3 ink-up"
      style={{ animationDelay: `${delay}ms` }}
    >
      <div
        className="font-display text-editorial-ivory text-[88px] leading-[0.85]"
        style={{ fontVariationSettings: "'opsz' 144, 'wght' 300, 'SOFT' 0" }}
      >
        {typeof value === 'number' ? pad2(value) : value}
      </div>
      <div className="font-mono text-[10px] text-editorial-ivory-mute tracking-wide-eyebrow uppercase">
        {label}
      </div>
    </div>
  )
}

/** Marquee ticker — only renders while a generation is in flight. */
function NowShowingMarquee({ latest }: { latest: ProgressEvent | null }) {
  const stage = latest?.stage ?? 'IDLE'
  const detail = latest?.detail ?? ''
  const percent = Math.round(latest?.percent ?? 0)

  const fragments = [
    'NOW SHOWING',
    `STAGE ${stage}`,
    detail || '—',
    `${percent}%`,
    'NOW SHOWING',
    `STAGE ${stage}`,
    detail || '—',
    `${percent}%`,
  ]

  return (
    <div className="border-y border-editorial-curtain/40 bg-editorial-curtain/[0.04] overflow-hidden">
      <div className="marquee-track py-2.5">
        {fragments.map((f, i) => (
          <span
            key={i}
            className="font-mono text-[11px] text-editorial-curtain tracking-wide-eyebrow uppercase mx-12 flex items-center gap-3"
          >
            <span className="inline-block w-1.5 h-1.5 bg-editorial-curtain rounded-full flicker" />
            {f}
          </span>
        ))}
      </div>
    </div>
  )
}

/** Scene cue sheet — each scene rendered like a film print cue line. */
function SceneCueSheet({ project }: { project: Project }) {
  if (project.scenes.length === 0) {
    return (
      <div className="px-10 py-16 text-center">
        <div
          className="font-display text-editorial-ivory-faint text-3xl italic"
          style={{ fontVariationSettings: "'opsz' 96, 'wght' 300, 'SOFT' 30" }}
        >
          The reel is blank.
        </div>
        <div className="font-sans text-editorial-ivory-mute text-sm mt-3">
          Add a scene in the editor below to begin composition.
        </div>
      </div>
    )
  }

  return (
    <div className="px-10">
      <div className="grid grid-cols-[60px_1fr_120px_80px] gap-6 pb-3 border-b border-editorial-rule">
        <Eyebrow>Reel</Eyebrow>
        <Eyebrow>Scene</Eyebrow>
        <Eyebrow className="text-right">Shots</Eyebrow>
        <Eyebrow className="text-right">Length</Eyebrow>
      </div>
      <ul>
        {project.scenes
          .slice()
          .sort((a, b) => a.order - b.order)
          .map((scene, i) => (
            <li
              key={scene.id}
              className="grid grid-cols-[60px_1fr_120px_80px] gap-6 py-5 border-b border-editorial-rule group transition-colors hover:bg-editorial-ink-soft/40"
              style={{ animationDelay: `${300 + i * 60}ms` }}
            >
              <div
                className="font-display text-editorial-ivory text-2xl tabular-nums"
                style={{ fontVariationSettings: "'opsz' 24, 'wght' 400, 'SOFT' 50" }}
              >
                {pad2(i + 1)}
              </div>
              <div className="min-w-0">
                <div
                  className="font-display text-editorial-ivory text-xl leading-tight truncate"
                  style={{ fontVariationSettings: "'opsz' 24, 'wght' 500, 'SOFT' 30" }}
                >
                  {scene.title || 'Untitled scene'}
                </div>
                <div className="font-sans text-[12px] text-editorial-ivory-mute mt-1.5 flex items-center gap-3">
                  {scene.mood && (
                    <span className="uppercase tracking-wide-eyebrow text-editorial-brass">
                      {scene.mood}
                    </span>
                  )}
                  {scene.mood && scene.location_id && <span className="text-editorial-rule-bright">·</span>}
                  {scene.characters_present.length > 0 && (
                    <span>
                      {scene.characters_present.length} cast member
                      {scene.characters_present.length === 1 ? '' : 's'}
                    </span>
                  )}
                </div>
              </div>
              <div className="font-mono text-sm text-editorial-ivory-soft text-right tabular-nums self-center">
                {scene.num_shots || scene.shots?.length || 0}
              </div>
              <div className="font-mono text-sm text-editorial-ivory-soft text-right tabular-nums self-center">
                {scene.duration_seconds ? formatRuntime(scene.duration_seconds) : '—:—'}
              </div>
            </li>
          ))}
      </ul>
    </div>
  )
}

/* ─── Main shell ──────────────────────────────────────────────── */

export default function EditorialShell({
  project,
  config,
  events: _events,
  latest,
  isStreaming,
  generating,
  onBackToProjects,
  onGenerate,
  onCancel,
  onRefreshProject,
  apiBase,
}: EditorialShellProps) {
  const totalShots = useMemo(
    () => project.scenes.reduce((acc, s) => acc + (s.num_shots || s.shots?.length || 0), 0),
    [project.scenes],
  )
  const totalRuntime = useMemo(
    () => project.scenes.reduce((acc, s) => acc + (s.duration_seconds || 0), 0),
    [project.scenes],
  )

  // Project ID becomes the "FILM Nº" — short, monotype, gives the
  // editorial chrome a unique identifier per project.
  const reelNumber = project.id.slice(0, 4).toUpperCase()

  const inFlight = generating || isStreaming
  const status = inFlight
    ? 'PRINTING'
    : project.scenes.length === 0
    ? 'PRE-PRODUCTION'
    : 'READY TO PRINT'

  return (
    <div className="min-h-screen bg-editorial-ink text-editorial-ivory">
      {/* ── Top bar ── back link + reel marker ─────────────────── */}
      <div className="px-10 pt-8 pb-6 flex items-center justify-between border-b border-editorial-rule">
        <button
          onClick={onBackToProjects}
          className="font-mono text-[11px] text-editorial-ivory-mute tracking-wide-eyebrow uppercase hover:text-editorial-brass link-editorial"
        >
          ← The Archive
        </button>
        <div className="font-mono text-[11px] text-editorial-ivory-mute tracking-wide-eyebrow uppercase flex items-center gap-3">
          <span>Reel Nº</span>
          <span className="text-editorial-ivory">{reelNumber}</span>
          <span className="text-editorial-rule-bright">/</span>
          <span>{project.global_settings?.aspect_ratio || '9:16'}</span>
          <span className="text-editorial-rule-bright">/</span>
          <span
            className={
              inFlight
                ? 'text-editorial-curtain flicker'
                : project.scenes.length === 0
                ? 'text-editorial-ivory-mute'
                : 'text-editorial-brass'
            }
          >
            {status}
          </span>
        </div>
      </div>

      {/* ── Marquee — only while a take is being printed ───────── */}
      {inFlight && <NowShowingMarquee latest={latest} />}

      {/* ── Hero ── title + acts column ───────────────────────── */}
      <section className="px-10 pt-16 pb-12 grid grid-cols-12 gap-10">
        <div className="col-span-9 ink-up" style={{ animationDelay: '80ms' }}>
          <Eyebrow className="mb-6">A Cinema-Production Tool · Original Programme</Eyebrow>
          <h1
            className="font-display text-editorial-ivory text-[120px] leading-[0.88] tracking-tight-display"
            style={{ fontVariationSettings: "'opsz' 144, 'wght' 350, 'SOFT' 10" }}
          >
            {project.name || (
              <span className="italic text-editorial-ivory-faint">Untitled film</span>
            )}
          </h1>
          {project.global_settings?.music_mood && (
            <div className="mt-8 font-display-headline italic text-editorial-brass text-2xl">
              in the {project.global_settings.music_mood.toLowerCase()} register
            </div>
          )}
        </div>

        <aside
          className="col-span-3 flex flex-col gap-6 pl-8 border-l border-editorial-rule ink-up"
          style={{ animationDelay: '180ms' }}
        >
          <div>
            <Eyebrow>Direction</Eyebrow>
            <div
              className="font-display text-editorial-ivory text-2xl mt-2"
              style={{ fontVariationSettings: "'opsz' 24, 'wght' 400, 'SOFT' 30" }}
            >
              {config?.creative_llm_options?.find(
                (o) => o.value === project.global_settings?.creative_llm,
              )?.label || 'Auto'}
            </div>
          </div>
          <div>
            <Eyebrow>Palette</Eyebrow>
            <div
              className="font-display text-editorial-ivory text-2xl mt-2 capitalize"
              style={{ fontVariationSettings: "'opsz' 24, 'wght' 400, 'SOFT' 30" }}
            >
              {project.global_settings?.color_palette?.replace(/_/g, ' ') || '—'}
            </div>
          </div>
          <div>
            <Eyebrow>Seed</Eyebrow>
            <div className="font-mono text-editorial-ivory text-base mt-2 tabular-nums">
              {project.global_settings?.master_seed?.toString().padStart(6, '0') || '——————'}
            </div>
          </div>
        </aside>
      </section>

      {/* ── Editorial figures strip ──────────────────────────── */}
      <section className="px-10 pb-12 grid grid-cols-12 gap-10 border-b border-editorial-rule">
        <div className="col-span-9 grid grid-cols-4 gap-10 items-end">
          <Figure value={project.scenes.length} label="Scenes" delay={240} />
          <Figure value={totalShots} label="Shots" delay={300} />
          <Figure value={project.characters.length} label="Cast" delay={360} />
          <Figure value={project.locations.length} label="Locations" delay={420} />
        </div>
        <div className="col-span-3 flex items-end justify-end gap-8 pl-8 border-l border-editorial-rule">
          <div className="text-right">
            <Eyebrow>Total runtime</Eyebrow>
            <div
              className="font-display text-editorial-ivory text-[64px] leading-[0.85] tabular-nums mt-2"
              style={{ fontVariationSettings: "'opsz' 144, 'wght' 300, 'SOFT' 0" }}
            >
              {totalRuntime > 0 ? formatRuntime(totalRuntime) : '—:——'}
            </div>
          </div>
        </div>
      </section>

      {/* ── Scene cue sheet ──────────────────────────────────── */}
      <section className="py-10 border-b border-editorial-rule">
        <div className="px-10 flex items-end justify-between mb-8">
          <div>
            <Eyebrow className="mb-3">Cue Sheet</Eyebrow>
            <h2
              className="font-display text-editorial-ivory text-4xl"
              style={{ fontVariationSettings: "'opsz' 60, 'wght' 350, 'SOFT' 20" }}
            >
              The Programme
            </h2>
          </div>
          <div className="font-mono text-[11px] text-editorial-ivory-mute tracking-wide-eyebrow uppercase">
            in playback order
          </div>
        </div>
        <SceneCueSheet project={project} />
      </section>

      {/* ── Action bar — Generate / Download / Cancel ──────────── */}
      <section className="px-10 py-10 border-b border-editorial-rule flex items-end justify-between gap-10">
        <div className="max-w-xl">
          <Eyebrow className="mb-3">Tonight's Print</Eyebrow>
          <p
            className="font-display-body text-editorial-ivory-soft text-lg leading-relaxed italic"
            style={{ fontVariationSettings: "'opsz' 14, 'wght' 350, 'SOFT' 40" }}
          >
            {project.scenes.length === 0
              ? 'Compose at least one scene below before requesting a print. The projectionist is patient.'
              : inFlight
              ? 'The print is running. Watch the marquee for live cues. You may pause or cancel at any time.'
              : 'When the reel is ready, send it to the printer. A finished take will be available for download upon completion.'}
          </p>
        </div>

        <div className="flex items-center gap-4 flex-shrink-0">
          {!inFlight ? (
            <>
              <button
                onClick={onGenerate}
                disabled={project.scenes.length === 0}
                className="group relative px-8 py-4 font-mono text-[11px] tracking-wide-eyebrow uppercase
                           bg-editorial-curtain text-editorial-ivory border border-editorial-curtain
                           hover:bg-editorial-curtain-deep disabled:bg-editorial-ink-rise
                           disabled:text-editorial-ivory-faint disabled:border-editorial-rule
                           disabled:cursor-not-allowed transition-colors"
              >
                <span className="relative z-10">Print this Reel →</span>
              </button>
              {project.scenes.length > 0 && (
                <a
                  href={`${apiBase}/projects/${project.id}/export`}
                  className="px-6 py-4 font-mono text-[11px] tracking-wide-eyebrow uppercase
                             border border-editorial-rule text-editorial-ivory-soft
                             hover:border-editorial-brass hover:text-editorial-brass transition-colors"
                >
                  Download MP4
                </a>
              )}
            </>
          ) : (
            <button
              onClick={onCancel}
              className="px-8 py-4 font-mono text-[11px] tracking-wide-eyebrow uppercase
                         border border-editorial-curtain text-editorial-curtain
                         hover:bg-editorial-curtain hover:text-editorial-ivory transition-colors"
            >
              Strike the Print
            </button>
          )}
        </div>
      </section>

      {/* ── Existing 3-column editor grid ──────────────────────── */
        /* Kept verbatim so all working component logic continues to flow
           through CharacterPanel / LocationPanel / ScenePanel / SettingsPanel
           / GenerationPanel / PreviewPanel. The new editorial chrome above
           is the storefront; this is the workshop. */}
      <section>
        <div className="px-10 pt-12 pb-6 flex items-end justify-between">
          <div>
            <Eyebrow className="mb-3">The Workshop</Eyebrow>
            <h2
              className="font-display text-editorial-ivory text-4xl"
              style={{ fontVariationSettings: "'opsz' 60, 'wght' 350, 'SOFT' 20' " }}
            >
              Cast, locations, sound &amp; settings
            </h2>
          </div>
          <div className="font-mono text-[11px] text-editorial-ivory-mute tracking-wide-eyebrow uppercase">
            edit the script, then print
          </div>
        </div>

        <div className="grid grid-cols-12 gap-0 h-[calc(100vh-100px)] border-t border-editorial-rule">
          {/* Left: cast + locations */}
          <div className="col-span-3 border-r border-editorial-rule overflow-y-auto bg-editorial-ink-soft/40">
            <CharacterPanel project={project} config={config} onRefresh={onRefreshProject} />
            <div className="rule-hairline" />
            <LocationPanel project={project} config={config} onRefresh={onRefreshProject} />
            <div className="rule-hairline" />
            <ObjectPanel project={project} onRefresh={onRefreshProject} />
          </div>

          {/* Center: scenes (editing) */}
          <div className="col-span-6 overflow-y-auto bg-editorial-ink">
            <ScenePanel project={project} config={config} onRefresh={onRefreshProject} />
          </div>

          {/* Right: settings + generation + preview */}
          <div className="col-span-3 border-l border-editorial-rule overflow-y-auto bg-editorial-ink-soft/40">
            <SettingsPanel project={project} config={config} onRefresh={onRefreshProject} />
            <div className="rule-hairline" />
            <GenerationPanel
              project={project}
              events={_events}
              latest={latest}
              isGenerating={inFlight}
            />
            <div className="rule-hairline" />
            <PreviewPanel project={project} />
          </div>
        </div>
      </section>

      {/* ── Colophon ── footer credit, magazine-style ─────────── */}
      <footer className="px-10 py-8 border-t border-editorial-rule flex items-center justify-between">
        <div className="font-mono text-[10px] text-editorial-ivory-mute tracking-wide-eyebrow uppercase">
          Cinema Production Tool · No. {reelNumber} · A working print
        </div>
        <div className="font-mono text-[10px] text-editorial-ivory-mute tracking-wide-eyebrow uppercase">
          Set in Fraunces &amp; Be Vietnam Pro
        </div>
      </footer>
    </div>
  )
}
