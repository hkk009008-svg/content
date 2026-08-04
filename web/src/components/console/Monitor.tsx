import { useMemo } from 'react'
import TakeStrip from './TakeStrip'
import DirectorReviewCard from '../pipeline/DirectorReviewCard'
import type { Project, ShotState, DirectorReview } from '../../types/project'
import { shotRequiresLipsync } from '../../lib/lipsyncEvidence'

export interface MonitorProps {
  project: Project
  activeShotId: string | null
  shotStates: Map<string, Partial<ShotState>>
  apiBase?: string
  projectId?: string | null
  directorReview: DirectorReview | null
}

export default function Monitor({
  project,
  activeShotId,
  shotStates,
  apiBase,
  projectId,
  directorReview,
}: MonitorProps) {
  const activeState = useMemo(
    () => (activeShotId ? shotStates.get(activeShotId) : null),
    [activeShotId, shotStates]
  )

  // Resolve cascade metadata for the live take so TakeStrip can render the
  // fallback / engine badges in the live-run console (Session 6 wired this
  // into ReviewStage; this closes the deferred Monitor-side gap). NF-4
  // (P1-3): dialogue takes carry a SECOND record at metadata.lipsync_cascade
  // — the overlay lip-sync pass; cascade_metadata holds the video cascade.
  const {
    cascadeMetadata,
    lipsyncCascadeMetadata,
    lipsyncValidationState,
    hasDialogue,
  } = useMemo(() => {
    const none = {
      cascadeMetadata: null,
      lipsyncCascadeMetadata: null,
      lipsyncValidationState: null,
      hasDialogue: undefined,
    }
    const takeId = activeState?.take_id
    if (!activeShotId || !takeId) return none
    const shot = project.scenes
      .flatMap((s) => s.shots)
      .find((s) => s.id === activeShotId)
    if (!shot) return none
    const take = [
      ...(shot.keyframe_takes ?? []),
      ...(shot.motion_takes ?? []),
      ...(shot.performance_takes ?? []),
      ...(shot.postprocess_variants ?? []),
    ].find((t) => t.id === takeId)
    return {
      cascadeMetadata: take?.cascade_metadata ?? null,
      lipsyncCascadeMetadata: take?.metadata?.lipsync_cascade ?? null,
      lipsyncValidationState: take?.metadata?.lipsync_validation_state ?? null,
      hasDialogue: shotRequiresLipsync(shot)
        ? true
        : typeof take?.metadata?.has_dialogue === 'boolean'
          ? take.metadata.has_dialogue
          : undefined,
    }
  }, [activeShotId, activeState?.take_id, project.scenes])

  const keyframeUrl = activeState?.generated_image ?? null
  const videoUrl = activeState?.generated_video ?? null

  // Attempt to distinguish motion vs performance from take_kind
  const takeKind = activeState?.take_kind
  const performanceUrl = takeKind === 'performance' ? videoUrl : null
  const motionUrl = takeKind === 'motion' || (!takeKind && videoUrl) ? videoUrl : null

  return (
    <main className="col-span-7 px-6 py-6">
      <h2 className="text-eyebrow-lg uppercase tracking-wider text-dim mb-3 font-mono">
        Monitor
      </h2>

      {keyframeUrl || performanceUrl || motionUrl ? (
        <div className="shadow-viewport rounded border border-line overflow-hidden">
          <TakeStrip
            keyframeUrl={keyframeUrl}
            performanceUrl={performanceUrl}
            motionUrl={motionUrl}
            apiBase={apiBase}
            projectId={projectId}
            cascadeMetadata={cascadeMetadata}
            lipsyncCascadeMetadata={lipsyncCascadeMetadata}
            lipsyncValidationState={lipsyncValidationState}
            hasDialogue={hasDialogue}
          />
        </div>
      ) : (
        <div className="aspect-video rounded border border-line bg-viewport-fill shadow-viewport flex items-center justify-center">
          <div className="text-center text-xs text-dim font-mono">
            {activeShotId ? 'Waiting for first take…' : 'No active shot'}
          </div>
        </div>
      )}

      {directorReview && (
        <div className="mt-4">
          <DirectorReviewCard review={directorReview} />
        </div>
      )}
    </main>
  )
}
