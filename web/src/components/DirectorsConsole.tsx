/**
 * DirectorsConsole — layout shell composing the 6 extracted regions plus
 * an inline masthead.
 *
 * Layout: masthead (inline) → hero band → 3-column main (phases/monitor/
 *         telemetry) → filmstrip → notes
 *
 * The 6 region subcomponents live in ./console/:
 *   HeroShot, PhasesRail, Monitor, Telemetry, Filmstrip, Notes
 *
 * The masthead (project title, back button, active-stage label) stays as
 * inline JSX here — it is the layout shell, not a region.
 */

import type { Project } from '../types/project'
import { usePipelineState } from '../hooks/usePipelineState'
import HeroShot from './console/HeroShot'
import PhasesRail from './console/PhasesRail'
import Monitor from './console/Monitor'
import Telemetry from './console/Telemetry'
import Filmstrip from './console/Filmstrip'
import Notes from './console/Notes'

interface Props {
  project: Project | null
  onBack: () => void
}

export default function DirectorsConsole({ project, onBack }: Props) {
  const projectId = project?.id || null
  const {
    activeStage, stages, isPaused, failedShots,
    directorReview, shotStates, activeShotId, notesBuffer, isStreaming,
  } = usePipelineState(projectId)

  return (
    <div className="min-h-screen bg-console-bg text-console-ink">
      {/* MASTHEAD — project title, back button, active-stage label */}
      <header className="border-b border-console-rule px-6 py-4 flex items-center justify-between">
        <div>
          <button
            onClick={onBack}
            className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute hover:text-console-gold font-console-mono"
          >
            ← Back to setup
          </button>
          <h1 className="mt-1 text-2xl font-display text-console-gold">
            {project?.name || 'No project loaded'}
            <span className="ml-2 text-sm font-normal text-console-ink-dim font-console-mono">
              · The Director's Console
            </span>
          </h1>
        </div>
        <div className="text-right text-xs font-console-mono">
          <div className="text-console-ink-mute uppercase tracking-wide">Active stage</div>
          <div className="text-console-gold">
            {activeStage || '—'}
            {isPaused && <span className="ml-2 text-console-accent">[paused]</span>}
          </div>
        </div>
      </header>

      {/* HERO BAND */}
      {project && (
        <HeroShot
          project={project}
          activeShotId={activeShotId}
          shotStates={shotStates}
          projectId={projectId}
        />
      )}

      {/* 3-COLUMN MAIN — phases rail | monitor | telemetry */}
      <div className="grid grid-cols-12 gap-0 border-b border-console-rule">
        <PhasesRail
          stages={stages}
          activeStage={activeStage}
          isPaused={isPaused}
          failedShots={failedShots}
        />
        {project && (
          <Monitor
            project={project}
            activeShotId={activeShotId}
            shotStates={shotStates}
            projectId={projectId}
            directorReview={directorReview}
          />
        )}
        {project && (
          <Telemetry
            project={project}
            shotStates={shotStates}
            failedShots={failedShots}
            isStreaming={isStreaming}
            projectId={projectId}
          />
        )}
      </div>

      {/* FILMSTRIP */}
      {project && (
        <Filmstrip
          project={project}
          projectId={projectId}
        />
      )}

      {/* NOTES */}
      <Notes notesBuffer={notesBuffer} />
    </div>
  )
}
