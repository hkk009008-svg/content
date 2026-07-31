import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { SuccessState } from './SuccessState'

describe('SuccessState', () => {
  it('renders the message in a polite, announced status region', () => {
    render(<SuccessState message="Shot 3 approved." />)
    const region = screen.getByRole('status')
    expect(region).toHaveTextContent('Shot 3 approved.')
    expect(region).toHaveAttribute('aria-live', 'polite')
  })

  it('renders and fires the optional dismiss action', async () => {
    const onDismiss = vi.fn()
    render(<SuccessState message="Saved." onDismiss={onDismiss} />)
    await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('omits the dismiss action when none is given', () => {
    render(<SuccessState message="Saved." />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
