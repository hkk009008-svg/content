import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
describe('test harness', () => {
  it('renders and matches', () => {
    render(<div>cinemaker-test-ok</div>)
    expect(screen.getByText('cinemaker-test-ok')).toBeInTheDocument()
  })
})
