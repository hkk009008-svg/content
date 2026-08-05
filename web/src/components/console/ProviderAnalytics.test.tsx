import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectNoAxeViolations } from '../../test/a11y-setup'
import ProviderAnalytics from './ProviderAnalytics'

function response(scope: 'project' | 'routing'): Response {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      scope,
      scope_video_id: scope === 'project' ? 'project-1' : '',
      terminal_limit: 200,
      cost_basis: 'reconciled_estimate',
      by_provider: {
        runway: {
          key: 'runway',
          terminal_count: 6,
          active_count: 1,
          succeeded: scope === 'project' ? 5 : 2,
          failed_billed: scope === 'project' ? 1 : 4,
          failed_unbilled: 0,
          failed_observed: 0,
          accepted_unknown: 0,
          success_rate: scope === 'project' ? 5 / 6 : 2 / 6,
          average_terminal_latency_s: 120,
          p95_terminal_latency_s: 180,
          charged_cost_usd: 1.25,
          token_cost_usd: 0.25,
          active_reservation_usd: 0.5,
          sample_count: 6,
          health: {
            status: scope === 'project' ? 'degraded' : 'unhealthy',
            score: scope === 'project' ? 72 : 30,
            sample_minimum: 5,
            reasons: [scope === 'project' ? 'billed_failures:1' : 'success_rate_below_50_percent:0.333'],
          },
        },
      },
    }),
  } as Response
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('ProviderAnalytics', () => {
  it('shows durable cost, success, latency, reservations, and the routing-health scope', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) =>
      response(String(input).includes('scope=routing') ? 'routing' : 'project'),
    )
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    const { container } = render(<ProviderAnalytics projectId="project-1" isStreaming={false} />)

    expect(await screen.findByText('degraded · 72')).toBeInTheDocument()
    expect(screen.getByText('83%')).toBeInTheDocument()
    expect(screen.getByText('3.0m')).toBeInTheDocument()
    expect(screen.getByText('$1.2500')).toBeInTheDocument()
    expect(screen.getByText('$0.5000')).toBeInTheDocument()
    expect(screen.getByText(/not provider invoices/)).toBeInTheDocument()
    expect(screen.getByText('Estimated usage')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Evidence scope'), 'routing')
    expect(await screen.findByText('unhealthy · 30')).toBeInTheDocument()
    expect(screen.getByText(/AUTO video routing avoids engines scored unhealthy/)).toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/projects/project-1/provider-analytics?scope=routing',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))
    await expectNoAxeViolations(container)
  })
})
