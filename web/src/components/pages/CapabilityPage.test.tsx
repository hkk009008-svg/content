import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import CapabilityPage from './CapabilityPage'
import type { Project, CapabilityScorecard } from '../../types/project'

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

const emptyScorecard: CapabilityScorecard = {
  project_id: 'proj1234',
  tier: 'production',
  summary: { shots_total: 0, shots_clearing_all_bars: 0 },
  dimensions: [],
  routing: { first_try: 0, fallback: 0, silent_fallback: 0 },
  gates: {
    plan: { approved: 0, vetoed: 0, top_vetoes: [] },
    image: { approved: 0, vetoed: 0, top_vetoes: [] },
    motion: { approved: 0, vetoed: 0, top_vetoes: [] },
    final: { approved: 0, vetoed: 0, top_vetoes: [] },
  },
  lora_availability: {
    training_available: false,
    registration_available: false,
    consumer_available: false,
    policy: 'dormant',
  },
  lora: [],
  components: [],
  per_shot: [],
  provenance: [],
  media: null,
  future_dimensions: ['pod_health', 'budget'],
}

const readyScorecard: CapabilityScorecard = {
  project_id: 'proj1234',
  tier: 'production',
  summary: { shots_total: 3, shots_clearing_all_bars: 2 },
  dimensions: [
    { key: 'identity', label: 'Identity · GhostFaceNet', value: 0.82, bar: 0.6, pass: true, n_measured: 3 },
    { key: 'coherence', label: 'Coherence', value: 0.7, bar: 0.6, pass: true, n_measured: 3 },
    { key: 'motion', label: 'Motion fidelity', value: 0.55, bar: null, pass: true, n_measured: 2 },
    { key: 'lipsync', label: 'Lipsync · SyncNet', value: null, bar: 0.65, pass: null, n_measured: 0 },
  ],
  routing: { first_try: 2, fallback: 1, silent_fallback: 0 },
  gates: {
    plan: { approved: 3, vetoed: 0, top_vetoes: [] },
    image: { approved: 2, vetoed: 1, top_vetoes: [['low_identity', 1]] },
    motion: { approved: 3, vetoed: 0, top_vetoes: [] },
    final: { approved: 3, vetoed: 0, top_vetoes: [] },
  },
  lora_availability: {
    training_available: false,
    registration_available: false,
    consumer_available: false,
    policy: 'dormant',
  },
  lora: [{ char_id: 'char_1', strength: 0.55, score: 0.87, verdict: 'ok' }],
  components: [
    {
      id: 'final_assembly', title: 'Final video assembly', status: 'live',
      exposure: 'internal', spend_kind: 'compute_local',
      engaged_static: true, runtime_availability: 'available', runtime_reason: null,
      reason: 'Verified: a live production consumer and a passing evidence test are on file.',
    },
    {
      id: 'batch_scene_optimize', title: 'Cross-shot batched prompt optimization', status: 'stubbed',
      exposure: 'internal', spend_kind: 'paid_api',
      engaged_static: false, runtime_availability: 'not_applicable', runtime_reason: null,
      reason: 'Not wired: implemented but has no production caller yet.',
    },
    {
      id: 'lora_validation', title: 'Historical LoRA validation records', status: 'inactive',
      exposure: 'internal', spend_kind: 'none',
      engaged_static: false, runtime_availability: 'not_applicable', runtime_reason: null,
      reason: 'Deliberately unavailable by policy; historical records only.',
    },
  ],
  per_shot: [
    { shot_id: 'sc1_sh1', identity: 0.82, coherence: 0.7, motion: 0.55, lipsync: null, engine: 'KLING_NATIVE' },
  ],
  provenance: [
    { shot_id: 'sc1_sh1', engine: 'KLING_NATIVE', attempts: ['KLING_NATIVE'], fallback: false },
  ],
  media: null,
  future_dimensions: ['pod_health', 'budget'],
}

/** A component that claims `wired` (the AUTHORED status) but that the server
 *  could not validate a live consumer + evidence test for — the exact
 *  "wired on syntactic anchors alone" defect the manifest validator exists
 *  to catch. Must render as unavailable, never as if it were live. */
const unvalidatedWiredComponent: CapabilityScorecard['components'][number] = {
  id: 'ghost_capability', title: 'Ghost Capability', status: 'wired',
  exposure: 'api', spend_kind: 'paid_api',
  engaged_static: false, runtime_availability: 'not_applicable', runtime_reason: null,
  reason: "Claims 'wired' but no production consumer is recorded; no evidence test is recorded.",
}

function mockFetchOnce(data: CapabilityScorecard) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => data })))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('CapabilityPage', () => {
  it('shows the empty-state copy when the scorecard has shots_total: 0', async () => {
    mockFetchOnce(emptyScorecard)
    render(<CapabilityPage project={project} />)

    await waitFor(() => {
      expect(screen.getByText(/no capability data yet/i)).toBeInTheDocument()
    })
  })

  it('renders a Meter per dimension when the scorecard has dimensions', async () => {
    mockFetchOnce(readyScorecard)
    const { container } = render(<CapabilityPage project={project} />)

    await waitFor(() => {
      expect(container.querySelectorAll('[data-testid="dimension-meter"]')).toHaveLength(readyScorecard.dimensions.length)
    })
  })

  it('renders LoRA records as inactive history and never advertises a second-character action', async () => {
    mockFetchOnce(readyScorecard)
    render(<CapabilityPage project={project} />)

    await waitFor(() => {
      expect(screen.getByText('Historical LoRA records')).toBeInTheDocument()
    })
    expect(screen.getByText(
      'Training, registration, and production use are unavailable. Historical records are read-only.',
    )).toBeInTheDocument()
    expect(screen.queryByText(['Second-character', 'LoRA'].join(' '))).toBeNull()
    expect(screen.getByText('1 of 3 systems engaged')).toBeInTheDocument()
    expect(screen.getAllByText('inactive')).toHaveLength(1)
  })

  it('labels the identity dimension GhostFaceNet, never ArcFace', async () => {
    mockFetchOnce(readyScorecard)
    render(<CapabilityPage project={project} />)

    await waitFor(() => {
      expect(screen.getByText('Identity · GhostFaceNet')).toBeInTheDocument()
    })
    expect(screen.queryByText(/ArcFace/)).toBeNull()
  })

  it('renders a component that claims wired but failed consumer/test validation as unavailable, with its reason, never as live', async () => {
    const scorecard: CapabilityScorecard = {
      ...readyScorecard,
      components: [...readyScorecard.components, unvalidatedWiredComponent],
    }
    mockFetchOnce(scorecard)
    render(<CapabilityPage project={project} />)

    await waitFor(() => {
      expect(screen.getByText('Ghost Capability')).toBeInTheDocument()
    })
    // the failed-validation chip renders "unavailable", never the authored
    // "wired" claim as a badge
    expect(screen.getByText('unavailable')).toBeInTheDocument()
    expect(screen.queryByText('wired')).toBeNull()
    // the human next-action reason is visible on the page, not hover-only
    expect(screen.getByText(/no production consumer is recorded/i)).toBeInTheDocument()
    // still 1 of 4 — the unvalidated ghost capability never counts as engaged
    expect(screen.getByText('1 of 4 systems engaged')).toBeInTheDocument()
  })

  it('never renders a raw engine id, component slug, or internal note text in the operator view', async () => {
    const scorecard: CapabilityScorecard = {
      ...readyScorecard,
      components: [
        ...readyScorecard.components,
        {
          id: 'internal_slug_9e75373', title: 'Cross-dissolve at scene boundaries', status: 'wired',
          exposure: 'ui', spend_kind: 'compute_local',
          engaged_static: true, runtime_availability: 'available', runtime_reason: null,
          reason: 'Verified: a live production consumer and a passing evidence test are on file.',
        },
      ],
    }
    mockFetchOnce(scorecard)
    render(<CapabilityPage project={project} />)

    await waitFor(() => {
      expect(screen.getByText('Cross-dissolve at scene boundaries')).toBeInTheDocument()
    })
    // human title renders; the raw internal id/commit-hash-shaped slug never does
    expect(screen.queryByText(/internal_slug_9e75373/)).toBeNull()
    expect(screen.queryByText(/9e75373/)).toBeNull()
    // per-shot/provenance engine ids are humanized, not shown as raw SNAKE_CASE
    expect(screen.queryByText('KLING_NATIVE')).toBeNull()
    expect(screen.getAllByText('Kling Native').length).toBeGreaterThan(0)
  })

  it('shows a legacy "max" tier value as historical, not as an active tier', async () => {
    mockFetchOnce({ ...readyScorecard, tier: 'max' })
    render(<CapabilityPage project={project} />)

    await waitFor(() => {
      expect(screen.getByText('MAX (legacy)')).toBeInTheDocument()
    })
    expect(screen.queryByText('MAX')).toBeNull()
  })
})
