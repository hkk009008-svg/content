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
})
