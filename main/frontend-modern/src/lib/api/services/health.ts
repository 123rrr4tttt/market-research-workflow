import { httpGet } from '../client'
import { endpoints } from '../endpoints'
import type { DeepHealthResponse, HealthResponse } from '../../types'

export async function fetchHealth() {
  return httpGet<HealthResponse>(endpoints.health.root)
}

export async function fetchDeepHealth() {
  return httpGet<DeepHealthResponse>(endpoints.health.deep)
}
