import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Project } from '../../types/project'
import ReviewStage from './ReviewStage'
import { expectNoAxeViolations } from '../../test/a11y-setup'

function makeProject(): Project {
  return {
    id: 'p1',
    name: 'Truthful review',
    characters: [],
    locations: [],
    objects: [],
    global_settings: { aspect_ratio: '16:9', music_mood: '', color_palette: '', style_rules: {} },
    scenes: [{
      id: 'scene-1',
      order: 0,
      title: 'Opening',
      location_id: '',
      characters_present: [],
      action: '',
      dialogue: 'Hello',
      mood: '',
      camera_direction: '',
      duration_seconds: 4,
      num_shots: 1,
      shots: [{
        id: 'shot-1',
        prompt: 'A speaking portrait',
        camera: 'close-up',
        target_api: 'VEO_NATIVE',
        plan_status: 'approved',
        keyframe_takes: [],
        motion_takes: [{
          id: 'native-take',
          kind: 'motion',
          path: 'native.mp4',
          metadata: { has_dialogue: true },
          cascade_metadata: { engine: 'VEO_NATIVE', native_audio_generated: true },
        }],
        performance_takes: [],
        postprocess_variants: [],
        diagnostics: [],
      }],
    }],
  } as unknown as Project
}

describe('ReviewStage lip-sync evidence', () => {
  afterEach(cleanup)

  it('shows native dialogue audio without measurement as UNKNOWN in persisted review cards', () => {
    const action = vi.fn(async () => ({}))
    const refresh = vi.fn(async () => {})

    render(
      <ReviewStage
        project={makeProject()}
        activeStage="REVIEW"
        shotStates={new Map()}
        onApprovePlan={action}
        onRejectPlan={action}
        onGenerateKeyframe={action}
        onApproveKeyframe={action}
        onApprovePerformance={action}
        onGenerateMotion={action}
        onApproveFinal={action}
        onCorrect={action}
        onDiagnose={action}
        onRegenerate={action}
        onProceedToAssembly={action}
        onRefreshProject={refresh}
      />,
    )

    expect(screen.getAllByText('Native audio').length).toBeGreaterThan(0)
    expect(
      screen.getAllByRole('status', { name: 'Lip-sync validation: UNKNOWN' }).length,
    ).toBeGreaterThan(0)
    expect(screen.queryByText('Lip-sync PASS')).toBeNull()
  })

  it('shows dialogue-only applicability as UNKNOWN when every sync field is absent', () => {
    const project = makeProject()
    const shot = project.scenes[0].shots[0]
    const take = shot.motion_takes[0]
    shot.dialogue = 'Legacy shot-level dialogue.'
    take.metadata = {}
    delete take.cascade_metadata

    const action = vi.fn(async () => ({}))
    render(
      <ReviewStage
        project={project}
        activeStage="REVIEW"
        shotStates={new Map()}
        onApprovePlan={action}
        onRejectPlan={action}
        onGenerateKeyframe={action}
        onApproveKeyframe={action}
        onApprovePerformance={action}
        onGenerateMotion={action}
        onApproveFinal={action}
        onCorrect={action}
        onDiagnose={action}
        onRegenerate={action}
        onProceedToAssembly={action}
        onRefreshProject={vi.fn(async () => {})}
      />,
    )

    expect(
      screen.getAllByRole('status', { name: 'Lip-sync validation: UNKNOWN' }).length,
    ).toBeGreaterThan(0)
  })
})

describe('ReviewStage deferred provider recovery', () => {
  afterEach(cleanup)

  function stage(project: Project, onGenerateMotion: ReturnType<typeof vi.fn>) {
    const action = vi.fn(async () => ({}))
    return (
      <ReviewStage
        project={project}
        activeStage="REVIEW"
        shotStates={new Map()}
        onApprovePlan={action}
        onRejectPlan={action}
        onGenerateKeyframe={action}
        onApproveKeyframe={action}
        onApprovePerformance={action}
        onGenerateMotion={onGenerateMotion}
        onApproveFinal={action}
        onCorrect={action}
        onDiagnose={action}
        onRegenerate={action}
        onProceedToAssembly={action}
        onRefreshProject={vi.fn(async () => {})}
      />
    )
  }

  it('surfaces a persisted pending job after a project reload and routes the recovery action through the existing endpoint callback', async () => {
    const onGenerateMotion = vi.fn(async () => ({
      code: 'provider_job_deferred',
      error: 'Still pending',
    }))
    const initial = makeProject()
    const { rerender } = render(stage(initial, onGenerateMotion))
    expect(screen.queryByText('LTX Job Pending')).toBeNull()

    const reloaded = makeProject()
    reloaded.scenes[0].shots[0].approved_keyframe_take_id = 'keyframe-1'
    reloaded.scenes[0].shots[0].deferred_motion_job = {
      engine: 'LTX',
      status: 'pending',
      reason: 'LTX accepted the request and is still rendering.',
      job_id: 'job-safe-123',
      provider_status: 'IN_PROGRESS',
      attempts: ['LTX', 'LTX'],
      billed: true,
      duration_s: 8,
      updated_at: '2026-08-04T10:20:30Z',
    }
    rerender(stage(reloaded, onGenerateMotion))

    const pending = screen.getByRole('status', { name: 'LTX Job Pending' })
    expect(pending).toHaveTextContent('job-safe-123')
    expect(pending).toHaveTextContent('IN_PROGRESS')
    expect(pending).toHaveTextContent('Attempts: LTX → LTX')
    expect(pending).toHaveTextContent('does not start a fallback provider')
    expect(screen.queryByRole('button', { name: 'Generate Motion' })).toBeNull()

    const resume = screen.getByRole('button', { name: 'Check / Resume LTX Job' })
    expect(resume).not.toBeDisabled()
    fireEvent.click(resume)
    await waitFor(() => expect(onGenerateMotion).toHaveBeenCalledWith('shot-1'))
    await expectNoAxeViolations(document.body)
  })

  it('announces a persisted recovery-required job as an alert without offering a new-provider action', async () => {
    const project = makeProject()
    project.scenes[0].shots[0].deferred_motion_job = {
      engine: 'LTX',
      status: 'recovery_required',
      reason: 'The provider status could not be confirmed automatically.',
      job_id: 'job-safe-456',
      provider_status: 'UNKNOWN',
      billed: false,
    }
    const onGenerateMotion = vi.fn(async () => ({}))
    render(stage(project, onGenerateMotion))

    const recovery = screen.getByRole('alert', { name: 'LTX Job Recovery Required' })
    expect(recovery).toHaveTextContent('could not be confirmed automatically')
    expect(recovery).toHaveTextContent('Provider billing: not reported')
    expect(screen.getByRole('button', { name: 'Check / Resume LTX Job' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Generate Motion' })).toBeNull()
  })

  it('labels non-LTX provider ambiguity as a recovery check rather than claiming automatic resume', async () => {
    const project = makeProject()
    project.scenes[0].shots[0].deferred_motion_job = {
      engine: 'VEO_NATIVE',
      status: 'recovery_required',
      reason: 'Submission acknowledgement was lost.',
      provider_status: 'submission_unknown',
      billed: false,
    }
    const onGenerateMotion = vi.fn(async () => ({}))
    render(stage(project, onGenerateMotion))

    const recovery = screen.getByRole('alert', { name: 'VEO_NATIVE Job Recovery Required' })
    expect(recovery).toHaveTextContent('blocks fallback generation')
    expect(recovery).toHaveTextContent('Automatic recovery is unavailable')
    expect(screen.getByText('Manual Recovery Required')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Check / Resume LTX Job' })).toBeNull()
    await expectNoAxeViolations(document.body)
  })
})

describe('ReviewStage deferred keyframe recovery', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  function recoveryProject(): Project {
    const project = makeProject()
    project.scenes[0].shots[0].deferred_keyframe_job = {
      engine: 'COMFYUI',
      status: 'recovery_required',
      reason: 'Prompt cancellation could not be confirmed.',
      job_id: 'prompt-safe-789',
      provider_status: 'UNKNOWN',
    }
    return project
  }

  function renderRecoveryStage(
    project: Project,
    onGenerateKeyframe = vi.fn(async () => ({})),
    onRefreshProject = vi.fn(async () => {}),
  ) {
    const action = vi.fn(async () => ({}))
    render(
      <ReviewStage
        project={project}
        activeStage="KEYFRAME_REVIEW"
        shotStates={new Map()}
        onApprovePlan={action}
        onRejectPlan={action}
        onGenerateKeyframe={onGenerateKeyframe}
        onApproveKeyframe={action}
        onApprovePerformance={action}
        onGenerateMotion={action}
        onApproveFinal={action}
        onCorrect={action}
        onDiagnose={action}
        onRegenerate={action}
        onProceedToAssembly={action}
        onRefreshProject={onRefreshProject}
      />,
    )
  }

  it('announces durable keyframe recovery truth and disables keyframe creation', async () => {
    const onGenerateKeyframe = vi.fn(async () => ({}))
    renderRecoveryStage(recoveryProject(), onGenerateKeyframe)

    const recovery = screen.getByRole('alert', { name: 'Keyframe Job Recovery Required' })
    expect(recovery).toHaveTextContent('Status: recovery_required')
    expect(recovery).toHaveTextContent('Reason: Prompt cancellation could not be confirmed.')
    expect(recovery).toHaveTextContent('Job ID: prompt-safe-789')

    const generate = screen.getByRole('button', { name: 'Generate Keyframe' })
    expect(generate).toBeDisabled()
    fireEvent.click(generate)
    expect(onGenerateKeyframe).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Adjust prompts and create another keyframe take' })).toBeDisabled()
    await expectNoAxeViolations(document.body)
  })

  it('requires confirmation, posts the manual reconciliation, and refreshes only after success', async () => {
    const onRefreshProject = vi.fn(async () => {})
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    }))
    vi.stubGlobal('fetch', fetchMock)
    renderRecoveryStage(recoveryProject(), undefined, onRefreshProject)

    fireEvent.click(screen.getByRole('button', { name: 'Confirm Manual Reconciliation' }))

    expect(confirmSpy).toHaveBeenCalledWith(
      'Confirm that keyframe job prompt-safe-789 was reconciled manually? This clears the recovery block and does not create a new keyframe.',
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/projects/p1/shots/shot-1/keyframes/recovery/resolve',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmed: true }),
      },
    ))
    await waitFor(() => expect(onRefreshProject).toHaveBeenCalledTimes(1))
  })

  it('keeps the recovery block visible and reports a failed reconciliation inline', async () => {
    const onRefreshProject = vi.fn(async () => {})
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 409,
      json: async () => ({ error: 'Provider job is still active.' }),
    })))
    renderRecoveryStage(recoveryProject(), undefined, onRefreshProject)

    fireEvent.click(screen.getByRole('button', { name: 'Confirm Manual Reconciliation' }))

    expect(await screen.findByText('Provider job is still active. The keyframe recovery block remains in place.')).toBeVisible()
    expect(screen.getByRole('alert', { name: 'Keyframe Job Recovery Required' })).toBeVisible()
    expect(onRefreshProject).not.toHaveBeenCalled()
  })
})
