/**
 * DirectorsConsole — layout shell for the 7-region director's interface.
 *
 * Layout: masthead → hero band → 3-column main (phases/monitor/telemetry)
 *         → filmstrip → notes
 *
 * Each region is a self-contained subcomponent from ./console/:
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
    <div className="min-h-screen bg-editorial-ink text-editorial-ivory">
      {/* MASTHEAD — project title, back button, active-stage label */}
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
      <div className="grid grid-cols-12 gap-0 border-b border-editorial-rule">
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
