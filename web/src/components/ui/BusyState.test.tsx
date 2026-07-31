import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { BusyState } from './BusyState'

describe('BusyState', () => {
  it('announces the busy label in a polite, aria-busy status region', () => {
    render(<BusyState label="Regenerating shot" />)
    const region = screen.getByRole('status')
    expect(region).toHaveTextContent('Regenerating shot')
    expect(region).toHaveAttribute('aria-live', 'polite')
    expect(region).toHaveAttribute('aria-busy', 'true')
  })

  it('defaults to a generic label', () => {
    render(<BusyState />)
    expect(screen.getByText('Working')).toBeInTheDocument()
  })
})
