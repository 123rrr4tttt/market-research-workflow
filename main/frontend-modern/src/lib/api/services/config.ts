import { httpGet, httpPost } from '../client'
import { endpoints } from '../endpoints'
import type { EnvSettings } from '../../types'

export async function fetchEnvSettings() {
  return httpGet<EnvSettings>(endpoints.config.env)
}

export async function saveEnvSettings(payload: Record<string, string>) {
  return httpPost<{ updated?: string[] }>(endpoints.config.env, payload)
}
