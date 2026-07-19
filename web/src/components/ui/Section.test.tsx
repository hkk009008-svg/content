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
})
