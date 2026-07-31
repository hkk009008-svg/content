import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import SceneCueSheet from './SceneCueSheet'
import type { Project } from '../../types/project'

// SceneCueSheet reads only setPage/setFocusScene off usePage() — mock the
// context module so the double-click assertion can spy on both without a
// real <PageProvider> tree.
const setPage = vi.fn()
const setFocusScene = vi.fn()

vi.mock('../../context/PageContext', () => ({
  usePage: () => ({ page: 'setup', setPage, focusScene: null, setFocusScene }),
}))

function makeProject(): Project {
  return {
    id: 'proj1',
    name: 'Test Reel',
    characters: [],
    locations: [
      {
        id: 'loc1',
        name: 'Warehouse',
        description: '',
        reference_images: [],
        prompt_fragment: '',
        lighting: '',
        time_of_day: 'day',
        weather: 'clear',
        seed: 0,
      },
    ],
    objects: [],
    scenes: [
      {
        id: 'scene1',
        order: 0,
        title: 'Opening',
        location_id: 'loc1',
        characters_present: [],
        action: '',
        dialogue: '',
        mood: 'cinematic',
        camera_direction: '',
        duration_seconds: 5,
        num_shots: 2,
        shots: [],
      },
      {
        id: 'scene2',
        order: 1,
        title: 'Closing',
        location_id: '',
        characters_present: [],
        action: '',
        dialogue: '',
        mood: 'cinematic',
        camera_direction: '',
        duration_seconds: 5,
        num_shots: 1,
        shots: [],
      },
    ],
    global_settings: {
      aspect_ratio: '16:9',
      music_mood: '',
      color_palette: '',
      style_rules: {},
    },
  }
}

describe('SceneCueSheet', () => {
  beforeEach(() => {
    setPage.mockClear()
    setFocusScene.mockClear()
  })

  it('renders one row per scene', () => {
    render(<SceneCueSheet project={makeProject()} />)
    expect(screen.getByText('Opening')).toBeInTheDocument()
    expect(screen.getByText('Closing')).toBeInTheDocument()
  })

  it('double-clicking a row jumps to Edit focused on that scene', () => {
    render(<SceneCueSheet project={makeProject()} />)

    fireEvent.doubleClick(screen.getByText('Opening'))

    expect(setFocusScene).toHaveBeenCalledWith('scene1')
    expect(setPage).toHaveBeenCalledWith('edit')
  })

  it('does not jump on a single click', () => {
    render(<SceneCueSheet project={makeProject()} />)

    fireEvent.click(screen.getByText('Closing'))

    expect(setFocusScene).not.toHaveBeenCalled()
    expect(setPage).not.toHaveBeenCalled()
  })

  // Slice 13b: audit findings closed on this file were (1) an ad hoc empty
  // paragraph instead of the shared EmptyState primitive, and (2) a large
  // unused void below a short scene list. Covered below.
  it('renders the shared EmptyState (not a bespoke paragraph) with no scenes', () => {
    const empty: Project = { ...makeProject(), scenes: [] }
    render(<SceneCueSheet project={empty} />)

    // EmptyState's own grammar: an "Empty" micro-label + serif heading.
    expect(screen.getByText('Empty')).toBeInTheDocument()
    expect(screen.getByText('No scenes yet')).toBeInTheDocument()
    expect(screen.getByText(/left tree/i)).toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('does not render the production-summary footer when there are no scenes', () => {
    const empty: Project = { ...makeProject(), scenes: [] }
    render(<SceneCueSheet project={empty} />)

    expect(screen.queryByText(/scenes blocked/)).toBeNull()
  })

  it('fills the center column with a pinned production summary instead of leaving it blank', () => {
    const project: Project = {
      ...makeProject(),
      scenes: [
        {
          id: 'scene1',
          order: 0,
          title: 'Opening',
          location_id: 'loc1',
          characters_present: [],
          action: '',
          dialogue: '',
          mood: 'cinematic',
          camera_direction: '',
          duration_seconds: 5,
          num_shots: 2,
          shots: [
            { id: 'sh1', generated_video: 'out1.mp4' } as any,
            { id: 'sh2', generated_video: '' } as any,
          ],
        },
        {
          id: 'scene2',
          order: 1,
          title: 'Closing',
          location_id: '',
          characters_present: [],
          action: '',
          dialogue: '',
          mood: 'cinematic',
          camera_direction: '',
          duration_seconds: 7,
          num_shots: 1, // sized but not yet decomposed -- shots stays empty
          shots: [],
        },
      ],
    }
    render(<SceneCueSheet project={project} />)

    expect(screen.getByText('Aspect 16:9')).toBeInTheDocument()
    expect(screen.getByText('1/2 scenes blocked')).toBeInTheDocument()
    expect(screen.getByText(/3 shots planned/)).toBeInTheDocument()
    expect(screen.getByText(/1 generated/)).toBeInTheDocument()
    expect(screen.getByText('~12s runtime')).toBeInTheDocument()
  })
})
