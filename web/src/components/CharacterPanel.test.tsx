import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CharacterPanel from './CharacterPanel'
import type { Project } from '../types/project'

const project = {
  id: 'project-lora-history',
  name: 'History',
  characters: [{
    id: 'char-legacy',
    name: 'Legacy Character',
    description: 'A preserved character record',
    reference_images: Array.from({ length: 25 }, (_, i) => `/refs/${i}.jpg`),
    canonical_reference: '/refs/0.jpg',
    voice_id: '',
    ip_adapter_weight: 0.85,
    physical_traits: '',
    embedding_cache: '',
  }],
  locations: [],
  objects: [],
  scenes: [],
  global_settings: {
    aspect_ratio: '16:9',
    music_mood: '',
    color_palette: '',
    style_rules: {},
  },
} satisfies Project

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('CharacterPanel dormant LoRA history', () => {
  it('performs one status GET and never restores training actions from stale state', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => ({
      ok: true,
      json: async () => ({
        char_id: 'char-legacy',
        status: 'training',
        progress_percent: 63,
        lora_path: '/legacy/char.safetensors',
        quality_score: 0.72,
        rejected: true,
        quality_warning: false,
        error: 'historical worker stopped',
        training_available: false,
        registration_available: false,
        consumer_available: false,
        policy: 'dormant',
      }),
    }))
    vi.stubGlobal('fetch', fetchMock)

    render(<CharacterPanel project={project} config={null} onRefresh={vi.fn()} />)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/projects/project-lora-history/characters/char-legacy/lora-status',
    )
    expect(screen.getByText('Inactive')).toBeInTheDocument()
    expect(screen.getByText(
      'Training, registration, and production use are unavailable. Historical records are read-only.',
    )).toBeInTheDocument()
    expect(screen.getByText('Historical status: training')).toBeInTheDocument()
    expect(screen.getByText('Historical path: /legacy/char.safetensors')).toBeInTheDocument()
    expect(screen.getByText('Quality 0.72 · not used by production')).toBeInTheDocument()
    expect(screen.getByText('Historical verdict: rejected')).toBeInTheDocument()
    expect(screen.getByText('Historical error: historical worker stopped')).toBeInTheDocument()

    expect(screen.queryByRole('button', { name: /train lora|re-train|retry/i })).toBeNull()
    const dormantActionPath = ['train', 'lora'].join('-')
    expect(fetchMock.mock.calls.some(([url, init]) =>
      String(url).includes(dormantActionPath) || (init as RequestInit | undefined)?.method === 'POST'
    )).toBe(false)
  })
})
