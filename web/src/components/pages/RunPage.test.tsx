import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import RunPage from './RunPage'
import type { Project, PipelineAction, CheckpointInfo, PipelineQueueSnapshot } from '../../types/project'

/**
 * Slice 11c -- Run-page header run controls.
 *
 * Covers the ONLY thing this slice changed in RunPage.tsx: Pause/Resume/
 * Cancel are now gated on the server-derived `allowedActions`
 * (`web_server.py:_pipeline_action_authority`) instead of the locally-
 * derived `isPaused`/`isGenerating` booleans, and an idle project with a
 * resumable checkpoint gets an explicit "Resume" vs "Start new" choice
 * instead of the plain pause/resume/cancel trio -- neither button
 * silently does the other's job (`onResumeFromCheckpoint` vs
 * `onGenerate`).
 *
 * Every heavy child (stage rail, review/screening routing, scene cards,
 * monitor/telemetry/notes, filmstrip) is mocked to an inert marker --
 * this file does not re-test the activeStage routing contract (already
 * pinned as a "reproduced byte-for-byte from PipelineLayout" regression
 * in the component's own file doc) or any child component's own behavior.
 */

vi.mock('../pipeline/PipelineStageRail', () => ({ default: () => <div data-testid="mock-stage-rail" /> }))
vi.mock('../pipeline/ReviewStage', () => ({ default: () => <div data-testid="mock-review-stage" /> }))
vi.mock('../pipeline/ScreeningStage', () => ({ default: () => <div data-testid="mock-screening-stage" /> }))
vi.mock('../pipeline/SceneExecutionCard', () => ({ default: () => <div data-testid="mock-scene-card" /> }))
vi.mock('../pipeline/DirectorReviewCard', () => ({ default: () => <div data-testid="mock-director-review" /> }))
vi.mock('../pipeline/AssemblyGate', () => ({ default: () => <div data-testid="mock-assembly-gate" /> }))
vi.mock('../console/Monitor', () => ({ default: () => <div data-testid="mock-monitor" /> }))
vi.mock('../console/Telemetry', () => ({ default: () => <div data-testid="mock-telemetry" /> }))
vi.mock('../console/ProviderAnalytics', () => ({ default: () => <div data-testid="mock-provider-analytics" /> }))
vi.mock('../console/TraceConsole', () => ({ default: () => <div data-testid="mock-trace-console" /> }))
vi.mock('../console/Notes', () => ({ default: () => <div data-testid="mock-notes" /> }))
vi.mock('../shared/Filmstrip', () => ({ default: () => <div data-testid="mock-filmstrip" /> }))

const project: Project = {
  id: 'proj1234',
  name: 'Test Reel',
  characters: [],
  locations: [],
  objects: [],
  scenes: [],
  global_settings: { aspect_ratio: '16:9', music_mood: '', color_palette: '', style_rules: {} },
}

const asyncNoop = async () => {}
const noop = () => {}

function makeProps(overrides: Partial<React.ComponentProps<typeof RunPage>> = {}) {
  return {
    project,
    events: [],
    latest: null,
    stages: [],
    activeStage: null as string | null,
    shotStates: new Map(),
    directorReview: null,
    isGenerating: false,
    isPaused: false,
    failedShots: [],
    allowedActions: [] as PipelineAction[],
    checkpoint: null as CheckpointInfo | null,
    queue: null as PipelineQueueSnapshot | null,
    onBack: noop,
    onCancel: noop,
    onAbandonQueueJob: asyncNoop,
    onPause: noop,
    onResume: noop,
    onResumeFromCheckpoint: noop,
    onGenerate: noop,
    onApproveShotPlan: asyncNoop,
    onRejectShotPlan: asyncNoop,
    onGenerateKeyframe: asyncNoop,
    onApproveKeyframe: asyncNoop,
    onApprovePerformance: asyncNoop,
    onGenerateMotion: asyncNoop,
    onApproveFinal: asyncNoop,
    onRegenerateShot: asyncNoop,
    onRestartShot: asyncNoop,
    onCorrectShot: asyncNoop,
    onDiagnoseShot: asyncNoop,
    onProceedToAssembly: asyncNoop,
    onRefreshProject: noop,
    ...overrides,
  }
}

describe('RunPage -- header run controls are server-authoritative (Slice 11c)', () => {
  it('announces durable queue position and offers cancel without a second start', () => {
    const queue: PipelineQueueSnapshot = {
      job_id: '1234567890abcdef', project_id: project.id, state: 'queued', position: 3,
      requested_resume: false, resume_required: false, effective_resume: false,
      attempt_count: 0, created_at: '2026-08-05T00:00:00Z', updated_at: '2026-08-05T00:00:00Z',
      started_at: null, finished_at: null, lease_expires_at: null,
      cancel_requested: false, error: null,
    }
    render(<RunPage {...makeProps({ isGenerating: true, allowedActions: ['cancel'], queue })} />)

    expect(screen.getByRole('status')).toHaveTextContent('Queued — position 3')
    expect(screen.getByRole('status')).toHaveTextContent('Job 12345678')
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start new' })).toBeNull()
  })

  it('surfaces the explicit abandonment action only for an unverifiable expired owner', () => {
    const onAbandonQueueJob = vi.fn(async () => {})
    const queue: PipelineQueueSnapshot = {
      job_id: '1234567890abcdef1234567890abcdef', project_id: project.id,
      state: 'running', position: 0,
      requested_resume: false, resume_required: true, effective_resume: true,
      attempt_count: 1, created_at: '2026-08-05T00:00:00Z', updated_at: '2026-08-05T00:01:00Z',
      started_at: '2026-08-05T00:00:01Z', finished_at: null,
      lease_expires_at: '2026-08-05T00:00:30Z', cancel_requested: false,
      error: 'Worker heartbeat expired but owner fence is unverifiable; automatic recovery is blocked',
      operator_action: 'abandon_unverifiable',
    }

    render(<RunPage {...makeProps({ queue, onAbandonQueueJob })} />)
    fireEvent.click(screen.getByRole('button', { name: 'Abandon blocked job' }))

    expect(screen.getByRole('alert')).toHaveTextContent('owner fence is unverifiable')
    expect(onAbandonQueueJob).toHaveBeenCalledWith(queue.job_id)
  })

  it('idle with no checkpoint renders none of Resume/Pause/Cancel -- only Back', () => {
    render(<RunPage {...makeProps({ allowedActions: ['start'] })} />)

    expect(screen.queryByRole('button', { name: 'Resume' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Start new' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Back' })).toBeInTheDocument()
  })

  it('running (not paused, not at a gate) renders Pause + Cancel, not Resume', () => {
    render(<RunPage {...makeProps({ isGenerating: true, allowedActions: ['cancel', 'pause'] })} />)

    expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Resume' })).toBeNull()
  })

  it('paused renders Resume + Cancel, not Pause', () => {
    render(<RunPage {...makeProps({ isGenerating: true, isPaused: true, allowedActions: ['cancel', 'resume'] })} />)

    expect(screen.getByRole('button', { name: 'Resume' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull()
  })

  it('running at a review gate renders ONLY Cancel -- pause is withheld (Slice 11c)', () => {
    render(<RunPage {...makeProps({ isGenerating: true, allowedActions: ['cancel'] })} />)

    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Resume' })).toBeNull()
  })

  it('clicking Pause/Resume/Cancel calls the matching callback', () => {
    const onPause = vi.fn()
    const onResume = vi.fn()
    const onCancel = vi.fn()
    const { rerender } = render(
      <RunPage {...makeProps({ isGenerating: true, allowedActions: ['cancel', 'pause'], onPause, onCancel })} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
    expect(onPause).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledTimes(1)

    rerender(
      <RunPage {...makeProps({
        isGenerating: true, isPaused: true, allowedActions: ['cancel', 'resume'], onResume,
      })} />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Resume' }))
    expect(onResume).toHaveBeenCalledTimes(1)
  })

  describe('idle with a resumable checkpoint -- explicit resume-vs-new-run choice', () => {
    const checkpoint: CheckpointInfo = {
      resumable: true,
      completed_scenes: 2,
      total_scenes: 5,
      stage: 'MOTION',
      shots_done: 3,
      shots_failed: 1,
    }

    it('shows "Resume" and "Start new" instead of the plain pause/resume/cancel trio', () => {
      render(<RunPage {...makeProps({ allowedActions: ['start', 'resume_checkpoint'], checkpoint })} />)

      expect(screen.getByRole('button', { name: 'Resume' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: 'Start new' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Pause' })).toBeNull()
      expect(screen.queryByRole('button', { name: 'Cancel' })).toBeNull()
    })

    it('renders the checkpoint progress summary', () => {
      render(<RunPage {...makeProps({ allowedActions: ['start', 'resume_checkpoint'], checkpoint })} />)

      expect(screen.getByText(/2\/5 scenes done/)).toBeInTheDocument()
      expect(screen.getByText(/1 shot failed/)).toBeInTheDocument()
    })

    it('"Resume" calls onResumeFromCheckpoint, never onGenerate', () => {
      const onResumeFromCheckpoint = vi.fn()
      const onGenerate = vi.fn()
      render(<RunPage {...makeProps({
        allowedActions: ['start', 'resume_checkpoint'], checkpoint, onResumeFromCheckpoint, onGenerate,
      })} />)

      fireEvent.click(screen.getByRole('button', { name: 'Resume' }))

      expect(onResumeFromCheckpoint).toHaveBeenCalledTimes(1)
      expect(onGenerate).not.toHaveBeenCalled()
    })

    it('"Start new" calls onGenerate, never onResumeFromCheckpoint -- does not silently resume', () => {
      const onResumeFromCheckpoint = vi.fn()
      const onGenerate = vi.fn()
      render(<RunPage {...makeProps({
        allowedActions: ['start', 'resume_checkpoint'], checkpoint, onResumeFromCheckpoint, onGenerate,
      })} />)

      fireEvent.click(screen.getByRole('button', { name: 'Start new' }))

      expect(onGenerate).toHaveBeenCalledTimes(1)
      expect(onResumeFromCheckpoint).not.toHaveBeenCalled()
    })
  })
})
