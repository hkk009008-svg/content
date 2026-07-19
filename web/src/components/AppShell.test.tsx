import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import AppShell from './AppShell'
import { PageProvider } from '../context/PageContext'
import type { Project, ProgressEvent } from '../types/project'

// Isolate the shell's chrome + page-routing from the network-heavy real
// pages. SetupPage mounts six panels (some fetch on mount); RunPage pulls the
// full PipelineLayout tree; CapabilityPage renders the console. Mock them to
// simple markers. EditPage is left REAL (it's a lightweight LoadingState) so
// the tab-switch assertion exercises a genuine page.
vi.mock('./pages/SetupPage', () => ({
  default: () => <div data-testid="mock-setup">setup-page</div>,
}))
vi.mock('./pages/RunPage', () => ({
  default: () => <div data-testid="mock-run">run-page</div>,
}))
vi.mock('./pages/CapabilityPage', () => ({
  default: () => <div data-testid="mock-capability">capability-page</div>,
}))

const project: Project = {
  id: 'proj1234',
  name: 'Test Reel',
  characters: [],
  locations: [],
  objects: [],
  scenes: [],
  global_settings: {
    aspect_ratio: '16:9',
    music_mood: '',
    color_palette: '',
    style_rules: {},
  },
}

const asyncNoop = async () => {}
const noop = () => {}

function makeProps(overrides: Partial<React.ComponentProps<typeof AppShell>> = {}) {
  return {
    project,
    config: null,
    events: [] as ProgressEvent[],
    latest: null,
    isStreaming: false,
    generating: false,
    onBackToProjects: noop,
    onGenerate: noop,
    onCancel: noop,
    onRefreshProject: noop,
    apiBase: '/api',
    budgetHalt: null,
    onDismissBudgetHalt: noop,
    // pipeline (Run page) state + callbacks
    stages: [],
    activeStage: null,
    shotStates: new Map(),
    directorReview: null,
    isPaused: false,
    failedShots: [],
    onBack: noop,
    onPause: noop,
    onResume: noop,
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
    ...overrides,
  }
}

function renderShell(overrides: Partial<React.ComponentProps<typeof AppShell>> = {}) {
  return render(
    <PageProvider>
      <AppShell {...makeProps(overrides)} />
    </PageProvider>,
  )
}

describe('AppShell', () => {
  it('renders the four page-bar tabs', () => {
    renderShell()
    expect(screen.getByRole('button', { name: /Setup/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Edit/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Run/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Capability/ })).toBeInTheDocument()
  })

  it('defaults to the Setup page', () => {
    renderShell()
    expect(screen.getByTestId('mock-setup')).toBeInTheDocument()
    expect(screen.queryByTestId('mock-run')).not.toBeInTheDocument()
  })

  it('switches to the Edit page when the Edit tab is clicked', () => {
    const { container } = renderShell()
    // Setup is showing first.
    expect(screen.getByTestId('mock-setup')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Edit/ }))

    // The real EditPage marker is now shown; setup is gone.
    expect(container.querySelector('[data-page="edit"]')).toBeInTheDocument()
    expect(screen.queryByTestId('mock-setup')).not.toBeInTheDocument()

    // Scene-jump wiring is deferred to Task 6 — none exists yet.
    expect(container.querySelector('.scene-jump')).toBeNull()
  })

  it('renders the BudgetHaltBanner (role=alert) when budgetHalt is set', () => {
    const halt: ProgressEvent = {
      stage: 'BUDGET_EXCEEDED',
      detail: 'cap reached',
      percent: 100,
      spent: 12.5,
      budget: 10,
    }
    renderShell({ budgetHalt: halt })
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })

  it('does NOT render the budget banner when budgetHalt is null', () => {
    renderShell({ budgetHalt: null })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
