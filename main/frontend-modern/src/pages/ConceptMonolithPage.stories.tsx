import type { Meta, StoryObj } from '@storybook/react-vite'
import ConceptMonolithPage from './ConceptMonolithPage'

const meta = {
  title: 'Pages/ConceptMonolithPage',
  component: ConceptMonolithPage,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof ConceptMonolithPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
