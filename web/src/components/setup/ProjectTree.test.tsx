import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import ProjectTree from './ProjectTree'
import type { Project, AppConfig } from '../../types/project'

/**
 * ProjectTree is a token-styled shell around six pre-existing, separately
 * tested CRUD panels (CharacterPanel.test.tsx, ObjectPanel.test.tsx,
 * PreviewPanel.test.tsx, ...) -- per its own docstring, this slice restyles
 * /relocates them without touching their internal logic. Mocked here to
 * inert placeholders so this suite covers ONLY what ProjectTree itself is
 * responsible for: composition, prop forwarding, and the shell chrome
 * (header label, section dividers, footer).
 */
vi.mock('../CharacterPanel', () => ({ default: (p: any) => <div data-testid="mock-character-panel">{p.project.characters.length}</div> }))
vi.mock('../LocationPanel', () => ({ default: (p: any) => <div data-testid="mock-location-panel">{p.project.locations.length}</div> }))
vi.mock('../ObjectPanel', () => ({ default: (p: any) => <div data-testid="mock-object-panel">{(p.project.objects || []).length}</div> }))
vi.mock('../ScenePanel', () => ({ default: (p: any) => <div data-testid="mock-scene-panel">{p.project.scenes.length}</div> }))
vi.mock('../GenerationPanel', () => ({ default: (p: any) => <div data-testid="mock-generation-panel">{p.isGenerating ? 'live' : 'idle'}</div> }))
vi.mock('../PreviewPanel', () => ({ default: () => <div data-testid="mock-preview-panel" /> }))

function makeProject(): Project {
  return {
    id: 'proj1',
    name: 'Test Reel',
    characters: [{ id: 'c1' } as any],
    locations: [],
    objects: [],
    scenes: [],
    global_settings: { aspect_ratio: '16:9', music_mood: '', color_palette: '', style_rules: {} },
  } as unknown as Project
}

const CONFIG = {} as AppConfig

describe('ProjectTree', () => {
  it('renders the Project header and all six panels in order, forwarding props', () => {
    render(
      <ProjectTree
        project={makeProject()}
        config={CONFIG}
        events={[]}
        latest={null}
        isGenerating
        onRefresh={vi.fn()}
      />,
    )

    expect(screen.getByText('Project')).toBeInTheDocument()
    expect(screen.getByTestId('mock-character-panel')).toHaveTextContent('1')
    expect(screen.getByTestId('mock-location-panel')).toBeInTheDocument()
    expect(screen.getByTestId('mock-object-panel')).toBeInTheDocument()
    expect(screen.getByTestId('mock-scene-panel')).toBeInTheDocument()
    expect(screen.getByTestId('mock-generation-panel')).toHaveTextContent('live')
    expect(screen.getByTestId('mock-preview-panel')).toBeInTheDocument()

    // Bin order: character/location/object/scene panels, then a footer
    // (generation + preview) -- verified by DOM position so a future
    // reorder is caught.
    const order = screen.getAllByTestId(/mock-/).map((el) => el.getAttribute('data-testid'))
    expect(order).toEqual([
      'mock-character-panel',
      'mock-location-panel',
      'mock-object-panel',
      'mock-scene-panel',
      'mock-generation-panel',
      'mock-preview-panel',
    ])
  })
})
