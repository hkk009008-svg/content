import { describe, it, expect } from 'vitest'
import { stageTone } from './stageTone'

describe('stageTone', () => {
  it('maps DONE to the success token', () => {
    expect(stageTone('DONE')).toBe('text-ok')
  })

  it('maps ERROR to the failure token', () => {
    expect(stageTone('ERROR')).toBe('text-fail')
  })

  it('falls back to the muted token for unknown stages', () => {
    expect(stageTone('ZZZ')).toBe('text-mut')
  })
})
