import type { Meta, StoryObj } from '@storybook/react-vite'
import ConceptLabIndexPage from './ConceptLabIndexPage'

const meta = {
  title: 'Pages/ConceptLabIndexPage',
  component: ConceptLabIndexPage,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof ConceptLabIndexPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
