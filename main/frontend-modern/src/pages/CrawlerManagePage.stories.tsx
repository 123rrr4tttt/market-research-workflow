import type { Meta, StoryObj } from '@storybook/react-vite'
import { expect, mocked } from 'storybook/test'
import * as api from '../lib/api'
import CrawlerManagePage from './CrawlerManagePage'
import { pageDecorators, pageParameters } from './storybookPageUtils'

const meta = {
  title: 'Pages/CrawlerManagePage',
  component: CrawlerManagePage,
  parameters: pageParameters,
  decorators: pageDecorators,
} satisfies Meta<typeof CrawlerManagePage>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    projectKey: '',
  },
}

const crawler = {
  id: 1,
  project_key: 'crawler-story',
  name: 'Crawler story',
  status: 'enabled',
  provider: 'scrapy',
  source_uri: 'https://example.com/very-long-project-path/crawler-repository.git',
  deployed_version: 'v1',
}

export const Ready: Story = {
  args: { projectKey: 'demo-proj' },
  beforeEach: async () => {
    mocked(api.listCrawlerProjects).mockResolvedValue([crawler] as never)
    mocked(api.getCrawlerProjectDetail).mockResolvedValue(crawler as never)
    mocked(api.listCrawlerDeployRuns).mockResolvedValue([
      { id: 42, action: 'deploy', status: 'success', from_version: 'v0', to_version: 'v1', external_job_id: 'scrapyd-job-42', finished_at: '2026-10-05T08:00:00Z' },
    ] as never)
  },
  play: async ({ canvas, userEvent }) => {
    await expect(canvas.getByText('scrapyd-job-42')).toBeVisible()
    await userEvent.click(canvas.getByText('项目详情'))
    await expect(canvas.getByText(crawler.source_uri)).toBeVisible()
  },
}

export const Empty: Story = {
  args: { projectKey: 'demo-proj' },
  beforeEach: async () => {
    mocked(api.listCrawlerProjects).mockResolvedValue([] as never)
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('暂无 crawler 项目')).toBeVisible()
    await expect(canvas.getByRole('button', { name: '提交部署' })).toBeDisabled()
  },
}

export const ReadError: Story = {
  args: { projectKey: 'demo-proj' },
  beforeEach: async () => {
    mocked(api.listCrawlerProjects).mockRejectedValue(new Error('read failed'))
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText('采集器项目读取失败')).toBeVisible()
  },
}
