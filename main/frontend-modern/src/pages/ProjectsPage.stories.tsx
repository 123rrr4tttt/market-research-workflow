import type { Meta, StoryObj } from '@storybook/react-vite'
import { mocked } from 'storybook/test'
import * as api from '../lib/api'
import type { ProjectItem } from '../lib/types'
import ProjectsPage from './ProjectsPage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const readyProjects: ProjectItem[] = [
  {
    id: 1,
    project_key: 'demo-proj',
    name: 'Demo project',
    schema_name: 'project_demo_proj',
    enabled: true,
    is_active: true,
  },
]

const fallbackProjects: ProjectItem[] = [
  {
    id: 2,
    project_key: 'business_survey',
    name: 'Business Survey',
    schema_name: '',
    enabled: true,
    is_active: true,
  },
]

const meta = {
  title: 'Pages/ProjectsPage',
  component: ProjectsPage,
  parameters: pageParameters,
  decorators: pageDecorators,
  beforeEach: async () => {
    mocked(api.listProjects).mockResolvedValue([] as never)
  },
} satisfies Meta<typeof ProjectsPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectKey: 'demo-proj',
    onProjectChange: () => undefined,
  },
}

export const ReadyToSubmit: Story = {
  args: {
    projectKey: 'demo-proj',
    onProjectChange: () => undefined,
  },
  beforeEach: async () => {
    mocked(api.listProjects).mockResolvedValue(readyProjects as never)
  },
}

export const UnknownFallback: Story = {
  args: {
    projectKey: 'missing-proj',
    onProjectChange: () => undefined,
  },
  beforeEach: async () => {
    mocked(api.listProjects).mockResolvedValue(fallbackProjects as never)
  },
}
