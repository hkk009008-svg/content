import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Toggle } from './Toggle'

describe('Toggle', () => {
  it('fires onChange with negated value', async () => {
    const on = vi.fn(); render(<Toggle checked={false} onChange={on} aria-label="x" />)
    await userEvent.click(screen.getByRole('switch')); expect(on).toHaveBeenCalledWith(true)
  })
})
