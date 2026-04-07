import type { Meta, StoryObj } from '@storybook/react-vite'
import { mocked } from 'storybook/test'
import * as api from '../lib/api'
import ProjectsPage from './ProjectsPage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

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
