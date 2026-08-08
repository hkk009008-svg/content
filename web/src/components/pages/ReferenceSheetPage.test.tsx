import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, afterEach } from 'vitest'
import ReferenceSheetPage, {
  DELIVERY_CUTS,
  moveReference,
  referencesPastEveryCut,
} from './ReferenceSheetPage'
import type { IdentityReference, Project } from '../../types/project'

function ref(
  path: string,
  overrides: Partial<IdentityReference> = {},
): IdentityReference {
  return {
    path,
    yaw: 'front',
    expression: 'neutral',
    light: 'studio',
    framing: 'close',
    origin: 'photo',
    source_path: '',
    judged: 'unjudged',
    reason: '',
    roles: [],
    ...overrides,
  }
}

function projectWith(refs: IdentityReference[]): Project {
  return {
    id: 'proj1234',
    name: 'Test Reel',
    characters: [{
      id: 'char_a',
      name: 'Alice',
      description: '',
      reference_images: refs.map(r => r.path),
      canonical_reference: refs[0]?.path ?? '',
      multi_angle_refs: refs.map(r => r.path),
      identity_refs: refs,
    }],
    locations: [],
    objects: [],
    scenes: [],
    global_settings: {
      aspect_ratio: '16:9', music_mood: '', color_palette: '', style_rules: {},
    },
  }
}

afterEach(() => {
  vi.restoreAllMocks()
})

/* ── pure helpers ─────────────────────────────────────────────── */

describe('moveReference', () => {
  it('moves an entry without mutating the input', () => {
    const items = ['a', 'b', 'c']
    expect(moveReference(items, 2, 0)).toEqual(['c', 'a', 'b'])
    expect(items).toEqual(['a', 'b', 'c'])
  })

  it('refuses out-of-range targets rather than wrapping', () => {
    // A repeated click on the top item must be a no-op, not a silent jump to
    // the bottom — slot 0 is Kling's frontal image.
    const items = ['a', 'b']
    expect(moveReference(items, 0, -1)).toBe(items)
    expect(moveReference(items, 1, 2)).toBe(items)
  })
})

describe('referencesPastEveryCut', () => {
  it('names only the references no provider reads', () => {
    const widest = DELIVERY_CUTS.reduce((max, e) => Math.max(max, e.cut), 0)
    const refs = Array.from({ length: widest + 2 }, (_, i) => ref(`r${i}.jpg`))
    const orphans = referencesPastEveryCut(refs)
    expect(orphans).toHaveLength(2)
    expect(orphans[0].path).toBe(`r${widest}.jpg`)
  })

  it('counts positions after rejections, not before', () => {
    // A rejected reference does not occupy a slot, so rejecting one PROMOTES
    // everything behind it. Counting raw index would report an orphan that is
    // actually delivered.
    const widest = DELIVERY_CUTS.reduce((max, e) => Math.max(max, e.cut), 0)
    const refs = [
      ref('rejected.jpg', { judged: 'reject' }),
      ...Array.from({ length: widest }, (_, i) => ref(`r${i}.jpg`)),
    ]
    expect(referencesPastEveryCut(refs)).toEqual([])
  })
})

/* ── the page ─────────────────────────────────────────────────── */

describe('ReferenceSheetPage', () => {
  it('shows no identity score anywhere', async () => {
    // ADR-092: the scorer inverts rank off-angle — a real photograph of the
    // subject in profile scored 0.556 while a generated stranger scored 0.570.
    // A number that ranks a stranger above the subject is worse than none,
    // because it looks authoritative.
    render(<ReferenceSheetPage project={projectWith([ref('a.jpg'), ref('b.jpg')])} />)
    expect(screen.queryByText(/similarity/i)).toBeNull()
    expect(screen.queryByText(/\bscore\b/i)).toBeNull()
    expect(screen.queryByText(/0\.\d\d/)).toBeNull()
  })

  it('names the provenance of each reference instead', () => {
    render(<ReferenceSheetPage project={projectWith([
      ref('real.jpg', { origin: 'photo' }),
      ref('made_up.jpg', { origin: 'invented', source_path: 'front.jpg' }),
    ])} />)
    expect(screen.getByText('Photograph')).toBeTruthy()
    expect(screen.getByText('Invented')).toBeTruthy()
  })

  it('warns that an invented reference is a different person', () => {
    render(<ReferenceSheetPage project={projectWith([
      ref('made_up.jpg', { origin: 'invented', source_path: 'front.jpg' }),
    ])} />)
    expect(screen.getByText(/1 invented reference in use/i)).toBeTruthy()
    // Said twice on purpose: once as a set-level warning, once on the card, so
    // it is legible whether the user is scanning or inspecting.
    expect(screen.getAllByText(/plausible stranger/i)).toHaveLength(2)
  })

  it('says which references reach nothing at all', () => {
    const widest = DELIVERY_CUTS.reduce((max, e) => Math.max(max, e.cut), 0)
    const refs = Array.from({ length: widest + 1 }, (_, i) => ref(`r${i}.jpg`))
    render(<ReferenceSheetPage project={projectWith(refs)} />)
    expect(screen.getByText(/1 reference past every cut/i)).toBeTruthy()
  })

  it('does not claim an orphan when the set fits every cut', () => {
    // Control for the assertion above: the warning must be able to be absent.
    render(<ReferenceSheetPage project={projectWith([ref('a.jpg')])} />)
    expect(screen.queryByText(/past every cut/i)).toBeNull()
  })

  it('marks slot 0 as the frontal slot', () => {
    render(<ReferenceSheetPage project={projectWith([ref('a.jpg'), ref('b.jpg')])} />)
    const slots = screen.getByLabelText('Reference slots in delivery order')
    const [first, second] = within(slots).getAllByRole('listitem')
    expect(first.textContent).toMatch(/slot\s*0/)
    expect(first.textContent).toMatch(/frontal/i)
    // And only slot 0 — the marker names Kling's frontal upload, not a facet.
    expect(second.textContent).not.toMatch(/· frontal/i)
  })

  it('holds a reorder as a draft until it is saved', async () => {
    // A reorder is a generation change, not a display preference: slot 0 is
    // uploaded as Kling's frontal image. It must not fire on the arrow click.
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    render(<ReferenceSheetPage project={projectWith([ref('a.jpg'), ref('b.jpg')])} />)

    await userEvent.click(screen.getByLabelText('Move slot 1 earlier'))
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Save order' })).toBeTruthy()
  })

  it('sends order as its own total field, not implied by the patch list', async () => {
    // The route refuses an `order` that is not an exact permutation, so a
    // reorder can neither drop a reference by omission nor invent one.
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ updated: true, identity_refs: [], coverage: {}, delivered: {} }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    )
    render(<ReferenceSheetPage project={projectWith([ref('a.jpg'), ref('b.jpg')])} />)

    await userEvent.click(screen.getByLabelText('Move slot 1 earlier'))
    await userEvent.click(screen.getByRole('button', { name: 'Save order' }))

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1))
    const [url, init] = fetchSpy.mock.calls[0]
    expect(String(url)).toContain('/characters/char_a/references')
    const body = JSON.parse(String((init as RequestInit).body))
    expect(body.order).toEqual(['b.jpg', 'a.jpg'])
    expect(body.references.map((r: { path: string }) => r.path)).toEqual(['b.jpg', 'a.jpg'])
  })

  it('surfaces a refused save instead of reporting success', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: 'order must be an exact permutation' }), {
        status: 400, headers: { 'Content-Type': 'application/json' },
      }),
    )
    render(<ReferenceSheetPage project={projectWith([ref('a.jpg'), ref('b.jpg')])} />)

    await userEvent.click(screen.getByLabelText('Move slot 1 earlier'))
    await userEvent.click(screen.getByRole('button', { name: 'Save order' }))

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain('exact permutation'),
    )
    // And the draft is KEPT, so the user's work is not silently discarded.
    expect(screen.getByRole('button', { name: 'Save order' })).toBeTruthy()
  })

  it('tells a character with no references what that means', () => {
    render(<ReferenceSheetPage project={projectWith([])} />)
    expect(screen.getByText(/every video provider will invent a face/i)).toBeTruthy()
  })

  it('explains itself when the project has no characters', () => {
    const empty = projectWith([])
    empty.characters = []
    render(<ReferenceSheetPage project={empty} />)
    expect(screen.getByText(/no characters yet/i)).toBeTruthy()
  })
})

describe('changing the canonical', () => {
  it('is its own act, and says what else it changes', async () => {
    // The canonical leads every provider set AND is the identity-validation
    // anchor. ADR-092 measured that the scorer floors off-angle, so a turned
    // canonical fails correct footage. That consequence must be stated, not
    // discovered.
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ updated: true, identity_refs: [], coverage: {} }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      }),
    )
    render(<ReferenceSheetPage project={projectWith([
      ref('canon.jpg', { roles: ['canonical'] }),
      ref('profile.jpg', { yaw: 'profile' }),
    ])} />)

    const button = screen.getByLabelText('Make slot 1 the canonical')
    expect(button.getAttribute('title')).toMatch(/identity validation/i)
    expect(button.getAttribute('title')).toMatch(/ADR-092/)

    await userEvent.click(button)
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1))
    const body = JSON.parse(String((fetchSpy.mock.calls[0][1] as RequestInit).body))
    expect(body.canonical).toBe('profile.jpg')
  })

  it('offers no such button on the reference that already is canonical', () => {
    render(<ReferenceSheetPage project={projectWith([
      ref('canon.jpg', { roles: ['canonical'] }),
      ref('profile.jpg'),
    ])} />)
    expect(screen.getByLabelText('Make slot 0 the canonical').hasAttribute('disabled')).toBe(true)
    expect(screen.getByLabelText('Make slot 1 the canonical').hasAttribute('disabled')).toBe(false)
  })

  it('never sends `canonical` on an ordinary save', async () => {
    // A reorder must not silently change the validation anchor.
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ updated: true, identity_refs: [] }), {
        status: 200, headers: { 'Content-Type': 'application/json' },
      }),
    )
    render(<ReferenceSheetPage project={projectWith([ref('a.jpg'), ref('b.jpg')])} />)
    await userEvent.click(screen.getByLabelText('Move slot 1 earlier'))
    await userEvent.click(screen.getByRole('button', { name: 'Save order' }))
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1))
    const body = JSON.parse(String((fetchSpy.mock.calls[0][1] as RequestInit).body))
    expect(body).not.toHaveProperty('canonical')
  })
})
