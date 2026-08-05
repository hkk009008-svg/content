import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import TraceConsole from './TraceConsole'

function jsonResponse(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('TraceConsole', () => {
  it('searches within the current project and pages older safe trace events', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('before=40')) {
        return jsonResponse({
          events: [{
            event_id: 39,
            ts: '2026-08-05T00:00:00+00:00',
            level: 'INFO',
            logger: 'cinema.pipeline',
            message: 'Older task accepted',
            trace_id: 'job-1',
            scene_id: '',
            shot_id: 'shot-1',
            engine: 'RUNWAY_GEN4',
            fields: {},
          }],
          has_more: false,
          next_before_event_id: null,
        })
      }
      return jsonResponse({
        events: [{
          event_id: 41,
          ts: '2026-08-05T01:00:00+00:00',
          level: 'WARNING',
          logger: 'cinema.pipeline',
          message: url.includes('q=recovery') ? 'Recovery requires operator review' : 'Provider latency warning',
          trace_id: 'job-1',
          scene_id: 'scene-1',
          shot_id: 'shot-1',
          engine: 'RUNWAY_GEN4',
          fields: {},
        }],
        has_more: true,
        next_before_event_id: 40,
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    render(<TraceConsole projectId="project-1" isStreaming={false} />)

    expect(await screen.findByText('Provider latency warning')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Search trace messages and fields'), 'recovery')
    await user.selectOptions(screen.getByLabelText('Trace level'), 'WARNING')
    await user.click(screen.getByRole('button', { name: 'Search' }))

    expect(await screen.findByText('Recovery requires operator review')).toBeInTheDocument()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/projects/project-1/traces?q=recovery&level=WARNING'),
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ))

    await user.click(screen.getByRole('button', { name: 'Load older' }))
    expect(await screen.findByText('Older task accepted')).toBeInTheDocument()
    expect(screen.getByText('Recovery requires operator review')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('before=40'),
      expect.objectContaining({ signal: undefined }),
    )
  })
})
