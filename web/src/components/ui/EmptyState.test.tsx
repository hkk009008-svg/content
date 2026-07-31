import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('renders the message in a polite, announced status region', () => {
    render(<EmptyState message="No scenes yet" />)
    const region = screen.getByRole('status')
    expect(region).toHaveTextContent('No scenes yet')
    expect(region).toHaveAttribute('aria-live', 'polite')
  })

  it('uses the default title when none is given, and a custom one when it is', () => {
    render(<EmptyState message="m" />)
    expect(screen.getByText('Nothing here yet')).toBeInTheDocument()
  })

  it('renders and fires the optional action', async () => {
    const onClick = vi.fn()
    render(<EmptyState message="No takes" action={{ label: 'Generate one', onClick }} />)
    await userEvent.click(screen.getByRole('button', { name: 'Generate one' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('omits the action row when no action is given', () => {
    render(<EmptyState message="No takes" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
