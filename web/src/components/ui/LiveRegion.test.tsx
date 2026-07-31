import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { LiveRegion } from './LiveRegion'

describe('LiveRegion', () => {
  it('defaults to a visually-hidden polite status announcement', () => {
    render(<LiveRegion message="3 of 5 shots regenerated" />)
    const region = screen.getByRole('status')
    expect(region).toHaveTextContent('3 of 5 shots regenerated')
    expect(region).toHaveAttribute('aria-live', 'polite')
    expect(region).toHaveClass('sr-only')
  })

  it('renders role="alert" for assertive announcements', () => {
    render(<LiveRegion message="Budget halted the run" politeness="assertive" />)
    const region = screen.getByRole('alert')
    expect(region).toHaveAttribute('aria-live', 'assertive')
  })

  it('drops the sr-only class when visuallyHidden is false', () => {
    render(<LiveRegion message="visible now" visuallyHidden={false} />)
    expect(screen.getByRole('status')).not.toHaveClass('sr-only')
  })
})
