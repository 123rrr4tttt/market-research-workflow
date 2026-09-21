import { expect, test } from '@playwright/test'

type StoryIndexEntry = {
  id: string
  name: string
  tags?: string[]
  title: string
  type: string
}

type StoryIndex = {
  entries: Record<string, StoryIndexEntry>
}

type StoryResult = {
  hasPlay: boolean
  id: string
  name: string
  status: string
  title: string
}

test('renders every indexed story and executes every play function', async ({ page, request }, testInfo) => {
  test.setTimeout(10 * 60_000)

  const indexResponse = await request.get('/index.json')
  expect(indexResponse.ok(), `Storybook index failed with HTTP ${indexResponse.status()}`).toBeTruthy()
  const index = await indexResponse.json() as StoryIndex
  const stories = Object.values(index.entries)
    .filter((entry) => entry.type === 'story')
    .sort((left, right) => left.id.localeCompare(right.id))
  const playStoryCount = stories.filter((entry) => entry.tags?.includes('play-fn')).length

  expect(stories.length, 'Storybook must expose at least one story').toBeGreaterThan(0)
  expect(playStoryCount, 'Storybook must expose the interaction stories tagged play-fn').toBeGreaterThan(0)

  const results: StoryResult[] = []
  const failures: string[] = []
  for (const story of stories) {
    await test.step(`${story.title} / ${story.name}`, async () => {
      try {
        await page.goto(`/iframe.html?id=${encodeURIComponent(story.id)}&viewMode=story`, {
          waitUntil: 'domcontentloaded',
        })
        await page.waitForFunction(
          (storyId) => {
            const channel = (globalThis as typeof globalThis & {
              __STORYBOOK_ADDONS_CHANNEL__?: {
                data?: { storyFinished?: Array<{ status?: string, storyId?: string }> }
              }
            }).__STORYBOOK_ADDONS_CHANNEL__
            return channel?.data?.storyFinished?.some((event) => event.storyId === storyId)
          },
          story.id,
          { timeout: 30_000 },
        )
        const status = await page.evaluate((storyId) => {
          const channel = (globalThis as typeof globalThis & {
            __STORYBOOK_ADDONS_CHANNEL__?: {
              data?: { storyFinished?: Array<{ status?: string, storyId?: string }> }
            }
          }).__STORYBOOK_ADDONS_CHANNEL__
          const events = channel?.data?.storyFinished || []
          return [...events].reverse().find((event) => event.storyId === storyId)?.status || 'missing'
        }, story.id)
        results.push({
          hasPlay: Boolean(story.tags?.includes('play-fn')),
          id: story.id,
          name: story.name,
          status,
          title: story.title,
        })
        if (status !== 'success') failures.push(`${story.id}: Storybook reported ${status}`)
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        results.push({
          hasPlay: Boolean(story.tags?.includes('play-fn')),
          id: story.id,
          name: story.name,
          status: 'runner-error',
          title: story.title,
        })
        failures.push(`${story.id}: ${message}`)
      }
    })
  }

  await testInfo.attach('storybook-story-results.json', {
    body: Buffer.from(`${JSON.stringify({
      failed: failures.length,
      play_story_count: playStoryCount,
      results,
      story_count: stories.length,
    }, null, 2)}\n`),
    contentType: 'application/json',
  })
  expect(failures, failures.join('\n')).toEqual([])
})
