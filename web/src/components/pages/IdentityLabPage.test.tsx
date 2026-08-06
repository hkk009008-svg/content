import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { GpuWorkerStatus, Project } from '../../types/project'
import IdentityLabPage from './IdentityLabPage'

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('../../lib/api', () => ({
  apiGet: api.get,
  apiPost: api.post,
}))

vi.mock('../../lib/useMediaAsset', () => ({
  useMediaAsset: (url: string | null | undefined) => (
    url ? { state: 'ready', src: url } : { state: 'idle', src: null }
  ),
}))

const readyWorker: GpuWorkerStatus = {
  role: 'image',
  label: 'Image worker',
  configured: true,
  dedicated: true,
  state: 'ready',
  message: 'Ready',
  benchmark_state: 'passed',
  startup_ready: true,
  execution_proven: true,
}

vi.mock('../setup/inspector/GpuWorkersSection', () => ({
  GpuWorkersSection: ({
    onImageWorker,
  }: {
    onImageWorker?: (worker: GpuWorkerStatus | null) => void
  }) => (
    <button type="button" onClick={() => onImageWorker?.(readyWorker)}>
      Report worker ready
    </button>
  ),
}))

const project: Project = {
  id: 'project-1',
  name: 'Identity Test',
  characters: [],
  locations: [],
  objects: [],
  scenes: [],
  global_settings: {
    aspect_ratio: '1:1',
    music_mood: '',
    color_palette: '',
    style_rules: {},
  },
}

const methods = [
  {
    method: 'native_flux2',
    label: 'Native FLUX.2 Klein 4B',
    state: 'available',
    reason: 'Runs the fixed comparison.',
  },
  {
    method: 'flux2_character_lora',
    label: 'FLUX.2 character LoRA',
    state: 'available',
    reason: 'Runs the fixed text-only and LoRA arms.',
  },
  {
    method: 'pulid_flux2',
    label: 'PuLID for FLUX.2',
    state: 'blocked',
    reason: 'The adapter is incompatible.',
  },
] as const

const characters = [{
  character_id: 'character-a',
  name: 'Character A',
  eligible: true,
  reference_count: 4,
  reference_fingerprint: 'f'.repeat(64),
  references: [1, 2, 3, 4].map((index) => ({
    role: index === 1 ? 'canonical' : 'angle',
    sha256: String(index).repeat(64),
    size_bytes: index * 100,
    media_path: `reference-${index}.png`,
  })),
  reason: '',
}]

function cell(referenceCount: number, score: number | null = null) {
  return {
    cell_key: `native_flux2:r${referenceCount}:s0`,
    method: 'native_flux2',
    label: `${referenceCount} ${referenceCount === 1 ? 'reference' : 'references'}`,
    reference_count: referenceCount,
    seed: 0,
    state: 'succeeded',
    prompt_id: `prompt-${referenceCount}` as string | null,
    output_path: `identity/r${referenceCount}.png` as string | null,
    output_sha256: 'a'.repeat(64) as string | null,
    latency_ms: referenceCount * 100 as number | null,
    identity_score: score,
    identity_verdict: score === null ? 'unknown' : 'passed',
    safe_error: '',
  }
}

function loraCell(variant: 'control' | 'adapter', score: number | null = null) {
  const label = variant === 'control' ? 'Text-only control' : 'Character LoRA'
  return {
    cell_key: `flux2_lora:${variant}:s0`,
    method: 'flux2_character_lora',
    label,
    reference_count: 0,
    seed: 0,
    state: 'succeeded',
    prompt_id: `prompt-${variant}` as string | null,
    output_path: `identity/lora-${variant}.png` as string | null,
    output_sha256: 'b'.repeat(64) as string | null,
    latency_ms: 500 as number | null,
    identity_score: score,
    identity_verdict: score === null ? 'unknown' : 'passed',
    safe_error: '',
  }
}

function experiment(state: string = 'succeeded') {
  return {
    experiment_id: 'a'.repeat(32),
    character_id: 'character-a',
    method: 'native_flux2',
    state,
    cancel_requested: false,
    lora_consent: true,
    safe_error: '',
    created_at: 1_800_000_000,
    updated_at: 1_800_000_001,
    references: [],
    reference_count: 4,
    cells: [cell(1, 0.812), cell(2), cell(4, 0.934), loraCell('control'), loraCell('adapter', 0.955)],
  }
}

function list(experiments: ReturnType<typeof experiment>[] = []) {
  return {
    experiments,
    methods,
    characters,
    prompt: 'Fixed identity benchmark prompt.',
  }
}

function ok<T>(data: T, status = 200) {
  return { ok: true as const, status, data }
}

beforeEach(() => {
  api.get.mockReset()
  api.post.mockReset()
  api.get.mockResolvedValue(ok(list()))
  vi.stubGlobal('crypto', { randomUUID: () => '12345678-1234-1234-1234-1234567890ab' })
})

describe('IdentityLabPage', () => {
  it('requires worker proof and explicit LoRA consent and renders the blocked backend reason', async () => {
    render(<IdentityLabPage project={project} apiBase="/api" />)

    const run = await screen.findByRole('button', { name: 'Run native + LoRA comparison' })
    expect(run).toBeDisabled()
    expect(screen.getByText(/image worker must be Ready/)).toBeInTheDocument()
    expect(screen.getByText('The adapter is incompatible.')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Unavailable' })).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Unavailable' })[0]).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: 'Report worker ready' }))
    expect(run).toBeDisabled()
    expect(screen.getByText(/Confirm authorized use/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox'))

    expect(run).toBeEnabled()
    expect(screen.getByAltText('canonical identity reference 1')).toHaveAttribute(
      'src',
      '/api/projects/project-1/file?path=reference-1.png',
    )
    expect(screen.getByText(/111111111111/)).toBeInTheDocument()
  })

  it('binds LoRA consent to the selected character', async () => {
    api.get.mockResolvedValue(ok({
      ...list(),
      characters: [
        ...characters,
        {
          character_id: 'character-b',
          name: 'Character B',
          eligible: true,
          reference_count: 4,
          reference_fingerprint: 'e'.repeat(64),
          references: [1, 2, 3, 4].map((index) => ({
            role: index === 1 ? 'canonical' : 'angle',
            sha256: `b${index}`.repeat(32),
            size_bytes: index * 100,
            media_path: `character-b-reference-${index}.png`,
          })),
          reason: '',
        },
      ],
    }))
    render(<IdentityLabPage project={project} apiBase="/api" />)

    const run = await screen.findByRole('button', { name: 'Run native + LoRA comparison' })
    fireEvent.click(screen.getByRole('button', { name: 'Report worker ready' }))
    fireEvent.click(screen.getByRole('checkbox'))
    expect(run).toBeEnabled()

    fireEvent.change(screen.getByLabelText('Character'), { target: { value: 'character-b' } })

    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(run).toBeDisabled()
  })

  it('keeps the comparison unavailable when the LoRA benchmark is blocked', async () => {
    api.get.mockResolvedValue(ok({
      ...list(),
      methods: methods.map((method) => method.method === 'flux2_character_lora'
        ? { ...method, state: 'blocked' as const, reason: 'Inference benchmark not proven.' }
        : method),
    }))

    render(<IdentityLabPage project={project} apiBase="/api" />)

    expect(await screen.findByText('Inference benchmark not proven.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Run native + LoRA comparison' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Unavailable' })).toHaveLength(2)
  })

  it('labels the first runnable LoRA proof as a canary', async () => {
    api.get.mockResolvedValue(ok({
      ...list(),
      methods: methods.map((method) => method.method === 'flux2_character_lora'
        ? {
            ...method,
            state: 'canary' as const,
            reason: 'The first run trains and benchmarks the fixed candidate.',
          }
        : method),
    }))

    render(<IdentityLabPage project={project} apiBase="/api" />)

    expect(await screen.findByText('Canary')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Report worker ready' }))
    fireEvent.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: 'Run native + LoRA comparison' })).toBeEnabled()
  })

  it('renders the fixed 1/2/4 grid through project media URLs and keeps unknown scores literal', async () => {
    api.get.mockResolvedValue(ok(list([experiment()])))

    render(<IdentityLabPage project={project} apiBase="/api" />)

    expect(await screen.findByRole('heading', { name: '1 reference' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '2 references' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '4 references' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Text-only control' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Character LoRA' })).toBeInTheDocument()
    expect(screen.getAllByText('UNKNOWN').length).toBeGreaterThan(0)
    expect(screen.getByAltText('1 reference identity comparison')).toHaveAttribute(
      'src',
      '/api/projects/project-1/file?path=identity%2Fr1.png',
    )
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  it('creates with only character and retry key, then cancels with an empty body', async () => {
    const queued = experiment('queued')
    queued.cells = queued.cells.map((value) => ({
      ...value,
      state: 'pending',
      prompt_id: null,
      output_path: null,
      output_sha256: null,
      latency_ms: null,
      identity_score: null,
      identity_verdict: 'unknown',
    }))
    const cancelled = { ...queued, state: 'cancelled' }
    api.post
      .mockResolvedValueOnce(ok(queued, 202))
      .mockResolvedValueOnce(ok(cancelled))

    render(<IdentityLabPage project={project} apiBase="/api" />)
    const run = await screen.findByRole('button', { name: 'Run native + LoRA comparison' })
    fireEvent.click(screen.getByRole('button', { name: 'Report worker ready' }))
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(run)

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/api/projects/project-1/identity-experiments',
      {
        character_id: 'character-a',
        request_id: '123456781234123412341234567890ab',
        lora_consent: true,
        reference_fingerprint: 'f'.repeat(64),
      },
    ))
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    const cancel = await screen.findByRole('button', { name: 'Cancel' })
    expect(run).toBeDisabled()
    fireEvent.click(cancel)

    await waitFor(() => expect(api.post).toHaveBeenLastCalledWith(
      `/api/projects/project-1/identity-experiments/${'a'.repeat(32)}/cancel`,
      {},
    ))
    expect(await screen.findByRole('status')).toHaveTextContent('cancellation requested')
  })

  it('offers resume only for a recoverable terminal result', async () => {
    const blocked = experiment('blocked')
    api.get.mockResolvedValue(ok(list([blocked])))
    api.post.mockResolvedValue(ok({ ...blocked, state: 'queued' }, 202))

    render(<IdentityLabPage project={project} apiBase="/api" />)

    fireEvent.click(await screen.findByRole('button', { name: 'Resume' }))

    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      `/api/projects/project-1/identity-experiments/${'a'.repeat(32)}/resume`,
      {},
    ))
  })

  it('does not allow a replacement run while an unknown experiment exists', async () => {
    api.get.mockResolvedValue(ok(list([experiment('unknown')])))

    render(<IdentityLabPage project={project} apiBase="/api" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Report worker ready' }))

    expect(screen.getByRole('button', { name: 'Run native + LoRA comparison' })).toBeDisabled()
    expect(screen.getByText(/active identity comparison/)).toBeInTheDocument()
  })

  it('disables resume on history while a different experiment is active', async () => {
    const historical = experiment('blocked')
    const active = {
      ...experiment('queued'),
      experiment_id: 'b'.repeat(32),
    }
    api.get.mockResolvedValue(ok(list([historical, active])))

    render(<IdentityLabPage project={project} apiBase="/api" />)

    expect(await screen.findByRole('button', { name: 'Resume' })).toBeDisabled()
  })

  it('polls active detail and stops when the experiment becomes terminal', async () => {
    const queued = experiment('queued')
    const succeeded = experiment('succeeded')
    api.get
      .mockResolvedValueOnce(ok(list([queued])))
      .mockResolvedValueOnce(ok(succeeded))
    vi.useFakeTimers()

    try {
      render(<IdentityLabPage project={project} apiBase="/api" />)
      await act(async () => {
        await Promise.resolve()
      })
      expect(api.get).toHaveBeenCalledTimes(1)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000)
      })
      expect(api.get).toHaveBeenCalledWith(
        `/api/projects/project-1/identity-experiments/${'a'.repeat(32)}`,
      )
      expect(api.get).toHaveBeenCalledTimes(2)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(5000)
      })
      expect(api.get).toHaveBeenCalledTimes(2)
    } finally {
      vi.useRealTimers()
    }
  })
})
