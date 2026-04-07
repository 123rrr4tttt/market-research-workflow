import type { Meta, StoryObj } from '@storybook/react-vite'
import ConceptOrbitalPage from './ConceptOrbitalPage'

const meta = {
  title: 'Pages/ConceptOrbitalPage',
  component: ConceptOrbitalPage,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof ConceptOrbitalPage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}
