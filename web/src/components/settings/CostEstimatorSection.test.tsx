import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CostEstimatorSection } from './CostEstimatorSection'

/**
 * Slice 13b: the estimate fetch used to collapse ANY failure to `null`,
 * which is exactly what "haven't fetched yet" also looks like -- the panel
 * showed "Loading estimate..." forever with no way to tell a request had
 * already failed (audit: "states inconsistent or missing"). Covers the
 * loading/error/success trichotomy and a real, wired retry.
 */

function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    text: vi.fn(async () => JSON.stringify(payload)),
  } as unknown as Response
}

function expandSection() {
  fireEvent.click(screen.getByRole('button', { name: /Cost Estimator/i }))
}

afterEach(() => {
  cleanupGlobals()
})

function cleanupGlobals() {
  vi.unstubAllGlobals()
}

describe('CostEstimatorSection', () => {
  it('shows LoadingState (not a bare "Loading estimate..." paragraph) while the estimate is in flight', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {}))) // never resolves
    render(<CostEstimatorSection s={{}} />)

    expandSection()

    expect(screen.getByRole('status')).toBeInTheDocument()
    expect(screen.getByText('Loading estimate')).toBeInTheDocument()
  })

  it('distinguishes a failed fetch from still-loading -- shows ErrorState, not an indefinite loading label', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ error: 'cost engine unavailable' }, false, 503)))
    render(<CostEstimatorSection s={{}} />)

    expandSection()

    expect(await screen.findByRole('alert')).toHaveTextContent('cost engine unavailable')
    expect(screen.queryByText(/Loading estimate/i)).toBeNull()
  })

  it('retry is genuinely wired -- re-fetches and clears the error on success', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () => response({ error: 'cost engine unavailable' }, false, 503))
      .mockImplementationOnce(async () =>
        response({
          totals: { grand_total: 12.5 },
          per_shot: { avg: 0.2 },
          shot_count: 60,
          dialogue_shots: 30,
          by_provider: {},
          notes: [],
        }),
      )
    vi.stubGlobal('fetch', fetchMock)
    render(<CostEstimatorSection s={{}} />)

    expandSection()
    expect(await screen.findByRole('alert')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Retry/i }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(await screen.findByText('Total (production)')).toBeInTheDocument()
  })

  it('renders the breakdown on a successful estimate', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        response({
          totals: { grand_total: 42, video: 30 },
          per_shot: { avg: 0.7 },
          shot_count: 60,
          dialogue_shots: 20,
          by_provider: { GOOGLE_GEMINI_API: 42 },
          notes: ['some note'],
        }),
      ),
    )
    render(<CostEstimatorSection s={{}} />)

    expandSection()

    expect(await screen.findByText('some note')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText(/Loading estimate/i)).toBeNull()
  })
})
