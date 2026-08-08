import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
        onGeneratePerformance={action}
        onSkipPerformance={action}
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
        onGeneratePerformance={action}
        onSkipPerformance={action}
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
        onGeneratePerformance={action}
        onSkipPerformance={action}
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

  it('labels native Veo ambiguity as manual recovery rather than claiming automatic resume', async () => {
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

  it('resumes a persisted Runway task by ID without exposing a fresh-provider action', async () => {
    const project = makeProject()
    project.scenes[0].shots[0].approved_keyframe_take_id = 'keyframe-1'
    project.scenes[0].shots[0].deferred_motion_job = {
      engine: 'RUNWAY_GEN4',
      status: 'recovery_required',
      reason: 'Runway polling timed out while the paid task remained active.',
      job_id: 'runway-task-123',
      provider_status: 'RUNNING',
      billed: false,
    }
    const onGenerateMotion = vi.fn(async () => ({
      code: 'provider_job_deferred',
      error: 'Still running',
    }))
    render(stage(project, onGenerateMotion))

    const recovery = screen.getByRole('alert', { name: 'RUNWAY_GEN4 Job Recovery Required' })
    expect(recovery).toHaveTextContent('runway-task-123')
    expect(recovery).toHaveTextContent('uses this saved RUNWAY_GEN4 job')
    const resume = screen.getByRole('button', { name: 'Check / Resume RUNWAY_GEN4 Job' })
    fireEvent.click(resume)

    await waitFor(() => expect(onGenerateMotion).toHaveBeenCalledWith('shot-1'))
    expect(screen.queryByRole('button', { name: 'Generate Motion' })).toBeNull()
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
        onGeneratePerformance={action}
        onSkipPerformance={action}
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
    const fetchMock = vi.fn(async (
      _input: RequestInfo | URL,
      _init?: RequestInit,
    ) => ({
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

describe('ReviewStage performance review workflow', () => {
  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  function performanceProject({
    hasDrivingVideo = false,
    hasPerformanceTake = false,
  }: {
    hasDrivingVideo?: boolean
    hasPerformanceTake?: boolean
  } = {}): Project {
    const project = makeProject()
    const shot = project.scenes[0].shots[0]
    shot.dialogue = ''
    shot.motion_takes = []
    shot.driving_video_path = hasDrivingVideo ? 'performance_inputs/scene-1/shot-1/driving.mp4' : ''
    shot.performance_takes = hasPerformanceTake
      ? [{
          id: 'performance-old',
          kind: 'performance',
          path: 'performance/old.mp4',
          status: 'review_required',
          metadata: {
            driving_video_path: 'performance_inputs/scene-1/shot-1/driving-old.mp4',
          },
        }]
      : []
    return project
  }

  function renderPerformanceStage({
    project = performanceProject(),
    activeStage = 'PERFORMANCE_REVIEW',
    onGeneratePerformance = vi.fn(async () => ({ success: true })),
    onSkipPerformance = vi.fn(async () => ({ success: true })),
    onRefreshProject = vi.fn(async () => {}),
  }: {
    project?: Project
    activeStage?: string
    onGeneratePerformance?: ReturnType<typeof vi.fn>
    onSkipPerformance?: ReturnType<typeof vi.fn>
    onRefreshProject?: ReturnType<typeof vi.fn>
  } = {}) {
    const action = vi.fn(async () => ({}))
    const rendered = render(
      <ReviewStage
        project={project}
        activeStage={activeStage}
        shotStates={new Map()}
        onApprovePlan={action}
        onRejectPlan={action}
        onGenerateKeyframe={action}
        onApproveKeyframe={action}
        onApprovePerformance={action}
        onGeneratePerformance={onGeneratePerformance}
        onSkipPerformance={onSkipPerformance}
        onGenerateMotion={action}
        onApproveFinal={action}
        onCorrect={action}
        onDiagnose={action}
        onRegenerate={action}
        onProceedToAssembly={action}
        onRefreshProject={onRefreshProject}
      />,
    )
    return { ...rendered, onGeneratePerformance, onSkipPerformance, onRefreshProject }
  }

  it('exposes mutating controls only at the review stage that owns them', () => {
    renderPerformanceStage({ activeStage: 'PERFORMANCE_REVIEW' })

    expect(screen.queryByRole('button', { name: 'Generate Keyframe' })).toBeNull()
    expect(screen.queryByRole('button', {
      name: 'Adjust prompts and create another keyframe take',
    })).toBeNull()
    expect(screen.getByText('Changes available in Keyframe Review')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Generate performance' })).toBeVisible()

    cleanup()
    renderPerformanceStage({ activeStage: 'KEYFRAME_REVIEW' })

    expect(screen.getByRole('button', { name: 'Generate Keyframe' })).toBeVisible()
    expect(screen.getByRole('button', {
      name: 'Adjust prompts and create another keyframe take',
    })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Generate performance' })).toBeNull()
  })

  it('opens the checked upload control from the keyboard and refreshes only after a confirmed upload', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn(async (
      _input: RequestInfo | URL,
      _init?: RequestInit,
    ) => ({
      ok: true,
      status: 201,
      statusText: 'Created',
      text: async () => JSON.stringify({
        uploaded: true,
        path: 'performance_inputs/scene-1/shot-1/driving.mp4',
        requires_performance_regeneration: true,
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)
    const { container, onRefreshProject } = renderPerformanceStage()
    const requestStorageKey = 'cinema:performance-request:p1:shot-1'
    window.sessionStorage.setItem(requestStorageKey, 'old-request-id')

    const uploadButton = screen.getByRole('button', { name: 'Upload driving video' })
    const input = screen.getByLabelText('Driving video file for shot shot-1') as HTMLInputElement
    expect(input).toHaveAttribute('tabindex', '-1')
    const inputClick = vi.spyOn(input, 'click')
    uploadButton.focus()
    await user.keyboard('{Enter}')

    expect(uploadButton).toHaveFocus()
    expect(inputClick).toHaveBeenCalledTimes(1)
    inputClick.mockRestore()

    const file = new File(['checked-video'], 'driving.mp4', { type: 'video/mp4' })
    await user.upload(input, file)

    await waitFor(() => expect(onRefreshProject).toHaveBeenCalledTimes(1))
    expect(window.sessionStorage.getItem(requestStorageKey)).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, request] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/projects/p1/shots/shot-1/upload-driving-video')
    expect(request).toMatchObject({ method: 'POST' })
    const uploadedFile = (request?.body as FormData).get('driving_video') as File
    expect(uploadedFile.name).toBe('driving.mp4')
    expect(uploadedFile.type).toBe('video/mp4')
    expect(screen.getByRole('status')).toHaveTextContent(
      'Driving video uploaded. Generate and approve a new performance take.',
    )
    expect(screen.getByText(/Uploads may be up to 30 seconds/)).toHaveTextContent(
      'capped at the first 8.0 seconds (200 frames at 25 fps)',
    )
    await expectNoAxeViolations(container)
  })

  it('announces a rejected upload and does not refresh stale project state', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      text: async () => JSON.stringify({ error: 'Driving video failed full decode.' }),
    })))
    const { onRefreshProject } = renderPerformanceStage()
    const input = screen.getByLabelText('Driving video file for shot shot-1') as HTMLInputElement

    await user.upload(input, new File(['broken'], 'broken.mp4', { type: 'video/mp4' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Driving video failed full decode.')
    expect(onRefreshProject).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Upload driving video' })).toBeEnabled()
  })

  it('generates a performance take, refreshes, and announces the review requirement', async () => {
    const user = userEvent.setup()
    const onGeneratePerformance = vi.fn(async () => ({ success: true, take_id: 'performance-new' }))
    const { onRefreshProject } = renderPerformanceStage({
      project: performanceProject({ hasDrivingVideo: true }),
      onGeneratePerformance,
    })

    await user.click(screen.getByRole('button', { name: 'Generate performance' }))

    await waitFor(() => expect(onGeneratePerformance).toHaveBeenCalledWith('shot-1'))
    await waitFor(() => expect(onRefreshProject).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('status')).toHaveTextContent(
      'Performance take generated. Review and approve the new take.',
    )
  })

  it('keeps a failed retry in review and does not refresh as if it succeeded', async () => {
    const user = userEvent.setup()
    const onGeneratePerformance = vi.fn(async () => ({
      success: false,
      error: 'The paid performance attempt is still unresolved.',
    }))
    const { onRefreshProject } = renderPerformanceStage({
      project: performanceProject({ hasDrivingVideo: true, hasPerformanceTake: true }),
      onGeneratePerformance,
    })

    await user.click(screen.getByRole('button', { name: 'Retry performance' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The paid performance attempt is still unresolved.',
    )
    expect(onGeneratePerformance).toHaveBeenCalledWith('shot-1')
    expect(onRefreshProject).not.toHaveBeenCalled()
    expect(screen.getByRole('note')).toHaveTextContent(
      'The latest take preview is paired with its historical driving-video revision and cannot be approved.',
    )
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Generate Motion' })).toBeNull()
  })

  it('fails closed on legacy take provenance and exposes motion only in final review', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
    const project = performanceProject({ hasDrivingVideo: true, hasPerformanceTake: true })
    project.scenes[0].shots[0].approved_keyframe_take_id = 'keyframe-approved'
    delete project.scenes[0].shots[0].performance_takes?.[0].metadata?.driving_video_path
    const { rerender } = renderPerformanceStage({ project })

    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
    expect(screen.getByRole('note')).toHaveTextContent(
      'no recorded driving-video revision',
    )
    expect(screen.queryByRole('button', { name: 'Generate Motion' })).toBeNull()

    const action = vi.fn(async () => {})
    rerender(
      <ReviewStage
        project={project}
        activeStage="REVIEW"
        shotStates={new Map()}
        onApprovePlan={action}
        onRejectPlan={action}
        onGenerateKeyframe={action}
        onApproveKeyframe={action}
        onApprovePerformance={action}
        onGeneratePerformance={action}
        onSkipPerformance={action}
        onGenerateMotion={action}
        onApproveFinal={action}
        onCorrect={action}
        onDiagnose={action}
        onRegenerate={action}
        onProceedToAssembly={action}
        onRefreshProject={action}
      />,
    )
    expect(screen.getByRole('button', { name: 'Generate Motion' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull()
    expect(screen.queryByRole('button', { name: /driving video/i })).toBeNull()
    expect(screen.getByText('Input changes available in Performance Review')).toBeVisible()
  })

  it('fails closed when a take exists but the shot has no active driving revision', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
    renderPerformanceStage({
      project: performanceProject({
        hasDrivingVideo: false,
        hasPerformanceTake: true,
      }),
    })

    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
    expect(screen.getByRole('note')).toHaveTextContent(
      'no driving video is currently selected',
    )
  })

  it('disables both upload controls while the upload request is in flight', async () => {
    const user = userEvent.setup()
    let resolveUpload!: (value: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => {
      resolveUpload = resolve
    })))
    renderPerformanceStage()
    const input = screen.getByLabelText(
      'Driving video file for shot shot-1',
    ) as HTMLInputElement
    const button = screen.getByRole('button', { name: 'Upload driving video' })

    await user.upload(
      input,
      new File(['video'], 'driving.mp4', { type: 'video/mp4' }),
    )
    await waitFor(() => expect(button).toBeDisabled())
    expect(input).toBeDisabled()
    expect(input).toHaveAttribute('tabindex', '-1')

    resolveUpload({
      ok: true,
      status: 201,
      statusText: 'Created',
      text: async () => JSON.stringify({
        uploaded: true,
        path: 'performance_inputs/scene-1/shot-1/driving.mp4',
        requires_performance_regeneration: true,
      }),
    } as Response)
    await waitFor(() => expect(button).toBeEnabled())
  })

  it('announces refresh failure after upload instead of painting success', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: 'OK',
      text: async () => JSON.stringify({
        uploaded: true,
        unchanged: true,
        path: 'performance_inputs/scene-1/shot-1/driving.mp4',
        requires_performance_regeneration: false,
      }),
    })))
    renderPerformanceStage({
      onRefreshProject: vi.fn(async () => {
        throw new Error('refresh offline')
      }),
    })
    const input = screen.getByLabelText('Driving video file for shot shot-1')

    await user.upload(
      input,
      new File(['video'], 'driving.mp4', { type: 'video/mp4' }),
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Driving video uploaded, but project refresh failed: refresh offline',
    )
    expect(screen.queryByText(/already selected; approvals were unchanged/)).toBeNull()
  })

  it('requires explicit skip confirmation and announces the downstream fallback', async () => {
    const user = userEvent.setup()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const onSkipPerformance = vi.fn(async () => ({ success: true, skipped: true }))
    const { container, onRefreshProject } = renderPerformanceStage({
      project: performanceProject({ hasDrivingVideo: true }),
      onSkipPerformance,
    })

    const skipReason = screen.getByRole('textbox', { name: /Skip reason/ })
    const skipButton = screen.getByRole('button', { name: 'Skip performance' })
    expect(skipReason).toHaveAttribute('maxlength', '240')
    expect(skipButton).toBeDisabled()
    await user.type(skipReason, 'The acting reference is unusable')
    expect(skipButton).toBeEnabled()
    await user.click(skipButton)

    expect(confirmSpy).toHaveBeenCalledWith(
      'Skip performance capture for this shot? Reason: The acting reference is unusable\n\nMotion generation will continue without a performance-driving take.',
    )
    expect(onSkipPerformance).toHaveBeenCalledWith(
      'shot-1',
      'The acting reference is unusable',
    )
    await waitFor(() => expect(onRefreshProject).toHaveBeenCalledTimes(1))
    expect(screen.getByRole('status')).toHaveTextContent(
      'Performance explicitly skipped. Reason recorded: The acting reference is unusable. Downstream motion will run without a performance-driving take.',
    )
    await expectNoAxeViolations(container)
  })
})

