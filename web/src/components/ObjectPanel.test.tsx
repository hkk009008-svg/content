import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ObjectPanel from './ObjectPanel'
import type { Project, ProductObject } from '../types/project'

// ---------------------------------------------------------------------------
// scale_reference is stored on every ProductObject (domain/project_manager.py
// make_object, web_server.py api_add_object/api_update_object) and is now read
// back by llm/prompt_optimizer.py on BOTH optimizer paths — the heuristic
// obj_anchor in _fallback_optimize and the obj_lines block of the LLM
// user_prompt — alongside its siblings material_traits/surface_type/
// branding_constraints/texture_anchor. Audit 2026-07-30 (slice 9d) found it
// reader-less and presented it read-only; the reader landed in the follow-up,
// so the control is editable again and these tests pin that it round-trips.
// ---------------------------------------------------------------------------

const SCALE_PLACEHOLDER = 'fits in adult hand, ~24cm tall, hand-sized'

function makeObject(overrides: Partial<ProductObject> = {}): ProductObject {
  return {
    id: 'obj-1',
    name: 'Aurora Bottle',
    brand: 'Aurora Beverages',
    description: 'Tall cobalt-blue glass bottle with gold foil label',
    reference_images: [],
    canonical_reference: '',
    material_traits: 'cobalt-blue glass, gold foil label',
    surface_type: 'glossy',
    branding_constraints: 'logo always visible, centered',
    scale_reference: 'fits in adult hand, ~24cm tall',
    texture_anchor: "gold 'Aurora' wordmark",
    embedding_cache: '',
    ...overrides,
  }
}

function makeProject(objects: ProductObject[] = [makeObject()]): Project {
  return {
    id: 'project-objects',
    name: 'Objects test',
    characters: [],
    locations: [],
    objects,
    scenes: [],
    global_settings: {
      aspect_ratio: '16:9',
      music_mood: '',
      color_palette: '',
      style_rules: {},
    },
  }
}

function fetchOkJson(payload: unknown = {}) {
  return vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    ({ ok: true, json: async () => payload }) as unknown as Response)
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ObjectPanel scale_reference is editable and wired', () => {
  it('renders the stored scale_reference as an editable field', () => {
    vi.stubGlobal('fetch', fetchOkJson())
    render(<ObjectPanel project={makeProject()} onRefresh={vi.fn()} />)

    fireEvent.click(screen.getByText('Edit'))

    const input = screen.getByPlaceholderText(SCALE_PLACEHOLDER) as HTMLInputElement
    expect(input.readOnly).toBe(false)
    expect(input.value).toBe('fits in adult hand, ~24cm tall')
    expect(screen.queryByText('(read-only)')).toBeNull()
    expect(screen.queryByText(/stored for reference only/i)).toBeNull()
  })

  it('accepts edits to the scale_reference field', () => {
    vi.stubGlobal('fetch', fetchOkJson())
    render(<ObjectPanel project={makeProject()} onRefresh={vi.fn()} />)

    fireEvent.click(screen.getByText('Edit'))
    const input = screen.getByPlaceholderText(SCALE_PLACEHOLDER) as HTMLInputElement

    fireEvent.change(input, { target: { value: 'palm-sized, ~9cm tall' } })

    expect(input.value).toBe('palm-sized, ~9cm tall')
  })

  it('submits the edited scale_reference on save', async () => {
    const fetchMock = fetchOkJson()
    vi.stubGlobal('fetch', fetchMock)
    render(<ObjectPanel project={makeProject()} onRefresh={vi.fn()} />)

    fireEvent.click(screen.getByText('Edit'))
    fireEvent.change(
      screen.getByPlaceholderText(SCALE_PLACEHOLDER),
      { target: { value: 'palm-sized, ~9cm tall' } },
    )
    fireEvent.click(screen.getByText('Save'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/projects/project-objects/objects/obj-1',
      expect.objectContaining({ method: 'PUT' }),
    ))
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(init.body as string)
    expect(body.scale_reference).toBe('palm-sized, ~9cm tall')
  })
})

describe('ObjectPanel texture_anchor caption accuracy (slice 9d)', () => {
  it('no longer claims texture_anchor drives negative_constraints or triggers regen', () => {
    vi.stubGlobal('fetch', fetchOkJson())
    render(<ObjectPanel project={makeProject()} onRefresh={vi.fn()} />)

    fireEvent.click(screen.getByText('Edit'))

    expect(screen.queryByText(/drives the negative_constraints/i)).toBeNull()
    expect(screen.queryByText(/triggers regen/i)).toBeNull()
    expect(screen.getByText(
      "The features that MUST be preserved across every shot. Included in the generation "
      + "prompt as the object's identity anchor, alongside brand and material.",
    )).toBeInTheDocument()
  })
})
