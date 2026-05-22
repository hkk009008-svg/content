/**
 * DirectorsConsole — initial React shell for design/directors-console.html.
 *
 * SCOPE — minimal viable wire-up:
 *   - Reproduces the 5-region layout from the mockup (masthead / hero / phases
 *     rail / monitor / telemetry / filmstrip / notes).
 *   - Each region is a labeled stub with a TODO pointing to its data source.
 *   - Pulls from existing project + pipeline state via the standard hooks.
 *
 * NOT YET DONE (deliberate — these would each be their own slice):
 *   - Full visual fidelity to design/directors-console.html (would require new
 *     Tailwind tokens + a custom font load + ~600 LOC of styling)
 *   - Wire each panel to live data (scenes, identity scores, motion fidelity,
 *     timeline progress) — needs new selectors on PipelineState
 *   - Inline keyframe ↔ performance ↔ motion preview reel (the "monitor")
 *
 * The point of this slice is: the design exists as a route, the data shape is
 * documented at each region, and future work has a clear place to land.
 */

import type { Project } from '../types/project'
import { usePipelineState } from '../hooks/usePipelineState'


interface Props {
  project: Project | null
  onBack: () => void
}


export default function DirectorsConsole({ project, onBack }: Props) {
  // Wire to the live pipeline state. When no project is loaded yet, the
  // console renders empty regions instead of failing — matches the rest of
  // the editorial-cinema flow.
  const projectId = project?.id || null
  const pipeline = usePipelineState(projectId)
  const { activeStage, stages, isPaused, failedShots, directorReview, shotStates } = pipeline

  return (
    <div className="min-h-screen bg-editorial-ink text-editorial-ivory">
      {/* MASTHEAD — project title, current shot, hero status */}
      <header className="border-b border-editorial-rule px-6 py-4 flex items-center justify-between">
        <div>
          <button
            onClick={onBack}
            className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute hover:text-editorial-brass"
          >
            ← Back to setup
          </button>
          <h1 className="mt-1 text-2xl font-semibold text-editorial-brass">
            {project?.name || 'No project loaded'}
            <span className="ml-2 text-sm font-normal text-editorial-ivory-mute">
              · The Director's Console
            </span>
          </h1>
        </div>
        <div className="text-right text-xs">
          <div className="text-editorial-ivory-mute uppercase tracking-wide">Active stage</div>
          <div className="font-mono text-editorial-brass">
            {activeStage || '—'}
            {isPaused && <span className="ml-2 text-editorial-curtain">[paused]</span>}
          </div>
        </div>
      </header>

      {/* HERO — top banner with current shot snapshot. TODO: needs live shot fetch */}
      <section className="px-6 py-8 border-b border-editorial-rule">
        <div className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute">
          Hero shot — placeholder
        </div>
        <p className="mt-2 max-w-prose text-sm text-editorial-ivory-mute">
          TODO: surface the currently-active shot (image + scene title + delivery cue).
          Data source: <code>shotStates</code> + current scene from <code>project.scenes</code>.
        </p>
      </section>

      {/* MAIN GRID — phases rail | monitor | telemetry */}
      <div className="grid grid-cols-12 gap-0 border-b border-editorial-rule">

        {/* PHASES RAIL — left sidebar with stage progress */}
        <aside className="col-span-2 border-r border-editorial-rule px-4 py-6 bg-editorial-ink-soft/30">
          <h2 className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute mb-3">
            Phases
          </h2>
          <ul className="space-y-1.5 text-xs">
            {stages.map((stage) => (
              <li
                key={stage.id}
                className={`flex items-center gap-2 ${
                  stage.id === activeStage
                    ? 'text-editorial-brass font-semibold'
                    : stage.status === 'complete'
                      ? 'text-editorial-ready'
                      : 'text-editorial-ivory-mute'
                }`}
              >
                <span className="inline-block w-2 h-2 rounded-full bg-current opacity-60" />
                {stage.label}
              </li>
            ))}
          </ul>
        </aside>

        {/* MONITOR — central preview area. TODO: full keyframe→performance→motion reel */}
        <main className="col-span-7 px-6 py-6">
          <h2 className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute mb-3">
            Monitor
          </h2>
          <div className="aspect-video rounded border border-editorial-rule bg-editorial-ink flex items-center justify-center">
            <div className="text-center text-xs text-editorial-ivory-mute">
              <div>TODO: side-by-side keyframe / performance / motion preview</div>
              <div className="mt-1">
                Data source: latest take from{' '}
                <code>shotStates[currentShotId]</code>
              </div>
            </div>
          </div>
          {directorReview && (
            <div className="mt-4 rounded border border-editorial-brass/30 bg-editorial-brass/5 px-4 py-3">
              <div className="text-eyebrow-lg uppercase tracking-wider text-editorial-brass">
                Director Review · {directorReview.decision}
              </div>
              <p className="mt-1 text-xs text-editorial-ivory-mute">{directorReview.reasoning}</p>
              {directorReview.violations.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-editorial-curtain">
                  {directorReview.violations.map((v, i) => <li key={i}>{v}</li>)}
                </ul>
              )}
            </div>
          )}
        </main>

        {/* TELEMETRY — right sidebar with quality scores */}
        <aside className="col-span-3 border-l border-editorial-rule px-4 py-6 bg-editorial-ink-soft/30">
          <h2 className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute mb-3">
            Telemetry
          </h2>
          <dl className="space-y-3 text-xs">
            <div>
              <dt className="text-editorial-ivory-mute uppercase text-eyebrow-lg">Shots</dt>
              <dd className="mt-0.5 font-mono text-editorial-brass">
                {project?.scenes?.reduce((sum, s) => sum + (s.shots?.length || 0), 0) || 0}
                <span className="text-editorial-ivory-mute ml-2 text-xs font-normal">
                  ({failedShots.length} failed)
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-editorial-ivory-mute uppercase text-eyebrow-lg">Active shot</dt>
              <dd className="mt-0.5 font-mono">
                {shotStates.size > 0 ? `${shotStates.size} tracked` : '—'}
              </dd>
            </div>
            {/* TODO: live cost ticker, current API/engine pick, gate scores */}
            <div className="rounded border border-editorial-rule bg-editorial-ink p-2 text-editorial-ivory-mute italic">
              TODO: live cost ticker · current engine · gate-score histogram
            </div>
          </dl>
        </aside>
      </div>

      {/* FILMSTRIP — horizontal scroller of completed shots */}
      <section className="px-6 py-6 border-b border-editorial-rule">
        <h2 className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute mb-3">
          Filmstrip
        </h2>
        <div className="overflow-x-auto">
          <div className="flex gap-2">
            {project?.scenes?.flatMap((scene) =>
              (scene.shots || []).map((shot) => (
                <div
                  key={shot.id}
                  className="shrink-0 w-32 aspect-video rounded border border-editorial-rule bg-editorial-ink relative overflow-hidden"
                  title={shot.prompt?.slice(0, 80)}
                >
                  {shot.generated_image ? (
                    <img
                      src={`/api/projects/${projectId}/file?path=${encodeURIComponent(shot.generated_image)}`}
                      className="w-full h-full object-cover"
                      alt=""
                    />
                  ) : (
                    <div className="w-full h-full flex items-center justify-center text-eyebrow-lg text-editorial-ivory-mute">
                      no take
                    </div>
                  )}
                  <div className="absolute bottom-0 left-0 right-0 bg-editorial-ink/80 px-1 py-0.5 text-eyebrow-lg text-editorial-ivory-mute">
                    {shot.id.slice(-6)}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </section>

      {/* NOTES — running operator log. TODO: feed from SSE event stream */}
      <section className="px-6 py-6">
        <h2 className="text-eyebrow-lg uppercase tracking-wider text-editorial-ivory-mute mb-3">
          Notes
        </h2>
        <div className="rounded border border-editorial-rule bg-editorial-ink p-3 text-xs text-editorial-ivory-mute italic">
          TODO: stream the latest 20 SSE events here as a director's running log
          (similar to GenerationPanel but visually richer per the mockup).
        </div>
      </section>
    </div>
  )
}
