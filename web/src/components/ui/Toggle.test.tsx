import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Toggle } from './Toggle'

describe('Toggle', () => {
  it('fires onChange with negated value', async () => {
    const on = vi.fn(); render(<Toggle checked={false} onChange={on} aria-label="x" />)
    await userEvent.click(screen.getByRole('switch')); expect(on).toHaveBeenCalledWith(true)
  })

  it('is keyboard-operable: Tab reaches it, Space/Enter toggle it', async () => {
    const onChange = vi.fn()
    render(<Toggle checked={false} onChange={onChange} aria-label="Enable feature" />)
    await userEvent.tab()
    expect(screen.getByRole('switch')).toHaveFocus()
    await userEvent.keyboard(' ')
    expect(onChange).toHaveBeenCalledWith(true)
    await userEvent.keyboard('{Enter}')
    expect(onChange).toHaveBeenCalledWith(true)
    expect(onChange).toHaveBeenCalledTimes(2)
  })

  it('is not focusable/operable while disabled', async () => {
    const onChange = vi.fn()
    render(<Toggle checked={false} onChange={onChange} disabled aria-label="Enable feature" />)
    await userEvent.tab()
    expect(screen.getByRole('switch')).not.toHaveFocus()
  })
})
