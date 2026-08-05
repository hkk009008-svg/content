import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { Badge } from './Badge'

describe('Badge', () => {
  it('local variant shows gear + local token class', () => {
    const { container } = render(<Badge variant="local">Local</Badge>)
    expect(screen.getByText(/Local/)).toBeInTheDocument()
    expect(container.firstChild).toHaveClass('text-local')
  })
})
