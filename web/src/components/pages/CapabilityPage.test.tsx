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
    { key: 'identity', label: 'Identity · ArcFace', value: 0.82, bar: 0.6, pass: true, n_measured: 3 },
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
  lora: [{ char_id: 'char_1', strength: 0.55, score: 0.87, verdict: 'ok' }],
  components: [
    { id: 'final_assembly', title: 'Final video assembly', status: 'live', note: '' },
    { id: 'batch_scene_optimize', title: 'Cross-shot batched prompt optimization', status: 'stubbed', note: 'zero callers' },
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
})
