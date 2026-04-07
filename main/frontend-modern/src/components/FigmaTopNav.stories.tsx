import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import FigmaTopNav, { type NavMode } from './FigmaTopNav'

const meta = {
  title: 'Navigation/FigmaTopNav',
  component: FigmaTopNav,
  decorators: [
    (Story) => (
      <div style={{ minHeight: 220 }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof FigmaTopNav>

export default meta

type Story = StoryObj<typeof meta>

const PROJECTS = ['demo-proj', 'market-watch', 'policy-tracker']

export const DarkTheme: Story = {
  render: function Render(args) {
    const [mode, setMode] = useState<NavMode>(args.mode)
    const [projectKey, setProjectKey] = useState(args.projectKey)

    return (
      <FigmaTopNav
        {...args}
        mode={mode}
        projectKey={projectKey}
        onModeChange={setMode}
        onProjectChange={setProjectKey}
      />
    )
  },
  args: {
    mode: 'dashboard',
    onModeChange: () => undefined,
    healthText: 'API Healthy',
    projectKey: 'demo-proj',
    projectOptions: PROJECTS,
    onProjectChange: () => undefined,
    theme: 'dark',
  },
}

export const BrandTheme: Story = {
  args: {
    mode: 'process',
    onModeChange: () => undefined,
    healthText: 'Worker Busy',
    projectKey: 'market-watch',
    projectOptions: PROJECTS,
    onProjectChange: () => undefined,
    theme: 'brand',
  },
}
