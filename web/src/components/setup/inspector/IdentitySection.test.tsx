import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { IdentitySection } from './IdentitySection'

describe('IdentitySection LoRA policy', () => {
  it('shows inactive/read-only truth and reference-based production guidance', () => {
    render(<IdentitySection s={{}} update={vi.fn()} />)

    expect(screen.getByText('Per-character LoRA')).toBeInTheDocument()
    expect(screen.getByText('Inactive')).toBeInTheDocument()
    expect(screen.getByText(
      'Training, registration, and production use are unavailable. Historical records are read-only.',
    )).toBeInTheDocument()
    expect(screen.getByText(/Gemini multi-reference first/)).toBeInTheDocument()
    expect(screen.getByText(/PuLID reference conditioning/)).toBeInTheDocument()
    expect(screen.queryByText(/RunPod/i)).toBeNull()
    expect(screen.queryByText(/Assign a LoRA/i)).toBeNull()
    expect(screen.queryByRole('button', { name: /train|assign/i })).toBeNull()
  })
})
