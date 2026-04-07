import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import FigmaSideNav, { type NavMode } from './FigmaSideNav'
import type { InteractionSurface } from '../app/topology/surfaces'

const meta = {
  title: 'Navigation/FigmaSideNav',
  component: FigmaSideNav,
  decorators: [
    (Story) => (
      <div style={{ minHeight: 720, maxWidth: 320 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FigmaSideNav>

export default meta

type Story = StoryObj<typeof meta>

export const Workbench: Story = {
  render: function Render(args) {
    const [mode, setMode] = useState<NavMode>(args.mode)
    const [surface, setSurface] = useState<InteractionSurface>(args.surface)

    return (
      <FigmaSideNav
        {...args}
        mode={mode}
        surface={surface}
        onModeChange={setMode}
        onSurfaceChange={setSurface}
      />
    )
  },
  args: {
    mode: 'flowWriting',
    onModeChange: () => undefined,
    surface: 'workbench',
    onSurfaceChange: () => undefined,
    theme: 'dark',
  },
}

export const Management: Story = {
  args: {
    mode: 'sysProjects',
    onModeChange: () => undefined,
    surface: 'management',
    onSurfaceChange: () => undefined,
    theme: 'brand',
  },
}
