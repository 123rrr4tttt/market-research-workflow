#!/usr/bin/env node
import { readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const distAssetsDir = join(process.cwd(), 'dist', 'assets')
const maxKb = Number(process.env.FORCE_GRAPH_VENDOR_MAX_KB || 2500)

function formatKb(bytes) {
  return (bytes / 1024).toFixed(1)
}

const files = readdirSync(distAssetsDir)
const targets = files.filter((name) => /force-graph-vendor.*\.(js|mjs)$/.test(name))

if (targets.length === 0) {
  console.error('[chunk-check] missing force-graph-vendor chunk in dist/assets')
  process.exit(1)
}

let failed = false
for (const file of targets) {
  const fullPath = join(distAssetsDir, file)
  const size = statSync(fullPath).size
  const kb = size / 1024
  const marker = kb > maxKb ? 'FAIL' : 'OK'
  console.log(`[chunk-check] ${marker} ${file} ${formatKb(size)}KB (limit ${maxKb}KB)`)
  if (kb > maxKb) failed = true
}

if (failed) {
  process.exit(1)
}

