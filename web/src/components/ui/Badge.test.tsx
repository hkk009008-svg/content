import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Badge } from './Badge'

describe('Badge', () => {
  it('pod variant shows gear + pod token class', () => {
    const { container } = render(<Badge variant="pod">Pod</Badge>)
    expect(screen.getByText(/Pod/)).toBeInTheDocument()
    expect(container.firstChild).toHaveClass('text-pod')
  })
})
