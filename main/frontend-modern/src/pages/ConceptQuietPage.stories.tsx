import type { Meta, StoryObj } from '@storybook/react-vite'
import ConceptQuietPage from './ConceptQuietPage'

const meta = {
  title: 'Pages/ConceptQuietPage',
  component: ConceptQuietPage,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof ConceptQuietPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
