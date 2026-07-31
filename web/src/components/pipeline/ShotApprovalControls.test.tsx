import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ShotApprovalControls from './ShotApprovalControls'

/**
 * Slice 8b (2026-07-30 comprehensive-unification plan, plan slice 8) --
 * before this change, `handleReject` called `setRejecting(false)`
 * unconditionally, regardless of whether the POST actually succeeded, so
 * a failed reject silently closed the rejection editor and discarded the
 * operator's typed reason. These tests pin the fix.
 */

function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    text: vi.fn(async () => JSON.stringify(payload)),
  } as unknown as Response
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('ShotApprovalControls -- truthful reject (Slice 8b requirement 5)', () => {
  it('a non-2xx reject keeps the rejection editor open with the typed reason and surfaces the error', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ error: 'Plan already finalized' }, false, 409)))
    const onAction = vi.fn()

    render(<ShotApprovalControls shot={{}} shotId="shot-1" projectId="proj-1" onAction={onAction} />)

    fireEvent.click(screen.getByRole('button', { name: /reject/i }))
    const reasonInput = screen.getByPlaceholderText('Rejection reason (optional)')
    fireEvent.change(reasonInput, { target: { value: 'blurry face' } })
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Plan already finalized')
    // Still in the rejecting sub-panel, reason preserved -- not torn down.
    expect(screen.getByDisplayValue('blurry face')).toBeInTheDocument()
    // Refresh still fires (Slice 8 requirement 5: refresh authoritative
    // state either way), it just doesn't close the panel.
    expect(onAction).toHaveBeenCalledTimes(1)
  })

  it('a network failure on reject keeps the editor open instead of throwing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))

    render(<ShotApprovalControls shot={{}} shotId="shot-1" projectId="proj-1" onAction={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /reject/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('offline')
    expect(screen.getByPlaceholderText('Rejection reason (optional)')).toBeInTheDocument()
  })

  it('a successful reject closes the rejection editor', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ rejected: true })))
    const onAction = vi.fn()

    render(<ShotApprovalControls shot={{}} shotId="shot-1" projectId="proj-1" onAction={onAction} />)

    fireEvent.click(screen.getByRole('button', { name: /reject/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Reject' }))

    await waitFor(() => expect(screen.queryByPlaceholderText('Rejection reason (optional)')).toBeNull())
    expect(onAction).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('a non-2xx approve surfaces an error without crashing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ error: 'Shot not found' }, false, 404)))
    const onAction = vi.fn()

    render(<ShotApprovalControls shot={{ identity_score: 0.9 }} shotId="shot-1" projectId="proj-1" onAction={onAction} />)

    fireEvent.click(screen.getByRole('button', { name: /approve/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Shot not found')
    expect(onAction).toHaveBeenCalledTimes(1)
  })
})
