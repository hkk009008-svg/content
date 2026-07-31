import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { OfflineState } from './OfflineState'

describe('OfflineState', () => {
  it('renders a polite, announced status region with a default connectivity message', () => {
    render(<OfflineState />)
    const region = screen.getByRole('status')
    expect(region).toHaveTextContent(/reach the server/i)
    expect(region).toHaveAttribute('aria-live', 'polite')
  })

  it('accepts a custom message', () => {
    render(<OfflineState message="Backend unreachable during resume." />)
    expect(screen.getByText('Backend unreachable during resume.')).toBeInTheDocument()
  })

  it('renders and fires retry when onRetry is given', async () => {
    const onRetry = vi.fn()
    render(<OfflineState onRetry={onRetry} />)
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('omits the retry action when onRetry is absent', () => {
    render(<OfflineState />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
