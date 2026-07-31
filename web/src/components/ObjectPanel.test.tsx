import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ObjectPanel from './ObjectPanel'
import type { Project, ProductObject } from '../types/project'

// ---------------------------------------------------------------------------
// scale_reference is stored on every ProductObject (domain/project_manager.py
// make_object, web_server.py api_add_object/api_update_object) but — unlike
// its siblings material_traits/surface_type/branding_constraints/
// texture_anchor, which llm/prompt_optimizer.py reads back into the object
// anchor/prompt (see obj_anchor / obj_lines) — nothing reads scale_reference
// back out. Audit 2026-07-30 flagged this as a decorative write; plan slice
// 9d. The field is presented read-only with a visible reason rather than
// left as a silently-inert editable control.
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
    ip_adapter_weight: 0.85,
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

describe('ObjectPanel scale_reference is read-only (slice 9d)', () => {
  it('renders the stored scale_reference as read-only with a visible reason', () => {
    vi.stubGlobal('fetch', fetchOkJson())
    render(<ObjectPanel project={makeProject()} onRefresh={vi.fn()} />)

    fireEvent.click(screen.getByText('Edit'))

    const input = screen.getByPlaceholderText(SCALE_PLACEHOLDER) as HTMLInputElement
    expect(input.readOnly).toBe(true)
    expect(input.value).toBe('fits in adult hand, ~24cm tall')
    expect(screen.getByText('(read-only)')).toBeInTheDocument()
    expect(screen.getByText(
      'Stored for reference only — not currently read by the generation prompt or camera '
      + 'framing, unlike the fields above.',
    )).toBeInTheDocument()
  })

  it('ignores attempted edits to the read-only scale_reference field', () => {
    vi.stubGlobal('fetch', fetchOkJson())
    render(<ObjectPanel project={makeProject()} onRefresh={vi.fn()} />)

    fireEvent.click(screen.getByText('Edit'))
    const input = screen.getByPlaceholderText(SCALE_PLACEHOLDER) as HTMLInputElement

    fireEvent.change(input, { target: { value: 'attempted edit' } })

    expect(input.value).toBe('fits in adult hand, ~24cm tall')
  })

  it('still submits the existing stored scale_reference unchanged on save', async () => {
    const fetchMock = fetchOkJson()
    vi.stubGlobal('fetch', fetchMock)
    render(<ObjectPanel project={makeProject()} onRefresh={vi.fn()} />)

    fireEvent.click(screen.getByText('Edit'))
    fireEvent.click(screen.getByText('Save'))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/projects/project-objects/objects/obj-1',
      expect.objectContaining({ method: 'PUT' }),
    ))
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const body = JSON.parse(init.body as string)
    expect(body.scale_reference).toBe('fits in adult hand, ~24cm tall')
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
