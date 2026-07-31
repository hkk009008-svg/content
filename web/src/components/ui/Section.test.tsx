import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { Section } from './Section'

describe('Section', () => {
  it('collapses on header click', async () => {
    render(<Section title="Video"><p>body</p></Section>)
    expect(screen.getByText('body')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: /Video/i }))
    expect(screen.queryByText('body')).toBeNull()
  })

  it('is keyboard-operable: Tab reaches the disclosure, Enter/Space toggle it', async () => {
    render(<Section title="Video"><p>body</p></Section>)
    await userEvent.tab()
    const disclosure = screen.getByRole('button', { name: /Video/i })
    expect(disclosure).toHaveFocus()
    expect(disclosure).toHaveAttribute('aria-expanded', 'true')

    await userEvent.keyboard('{Enter}')
    expect(disclosure).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('body')).toBeNull()

    await userEvent.keyboard(' ')
    expect(disclosure).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByText('body')).toBeVisible()
  })
})
