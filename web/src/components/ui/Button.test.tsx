import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Button } from './Button'

describe('Button', () => {
  it('is a native <button> and is keyboard-operable via Enter and Space', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Go</Button>)
    await userEvent.tab()
    expect(screen.getByRole('button', { name: 'Go' })).toHaveFocus()
    await userEvent.keyboard('{Enter}')
    await userEvent.keyboard(' ')
    expect(onClick).toHaveBeenCalledTimes(2)
  })

  it('is not focusable and does not fire onClick while disabled', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick} disabled>Go</Button>)
    await userEvent.tab()
    const button = screen.getByRole('button', { name: 'Go' })
    expect(button).not.toHaveFocus()
    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('marks itself aria-busy and disabled while isLoading', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick} isLoading>Go</Button>)
    const button = screen.getByRole('button', { name: 'Go' })
    expect(button).toHaveAttribute('aria-busy', 'true')
    expect(button).toBeDisabled()
    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })
})
