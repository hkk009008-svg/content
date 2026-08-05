import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { IdentitySection } from './IdentitySection'

describe('IdentitySection', () => {
  it('shows only active provider-neutral identity controls', () => {
    render(<IdentitySection s={{}} update={vi.fn()} />)

    expect(screen.getByText('Identity strictness')).toBeInTheDocument()
    expect(screen.getByText('Identity retry max')).toBeInTheDocument()
    expect(screen.getByText('Coherence threshold')).toBeInTheDocument()
    expect(screen.queryByText(/PuLID/i)).toBeNull()
    expect(screen.queryByText(/LoRA/i)).toBeNull()
    expect(screen.queryByText(/FLUX guidance/i)).toBeNull()
    expect(screen.queryByText(/RunPod/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /train|assign/i })).toBeNull()
  })
})
