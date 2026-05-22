#!/usr/bin/env node
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const rootDir = path.resolve(scriptDir, '..')
const repoRoot = path.resolve(rootDir, '..', '..')

const files = {
  writingDomain: 'src/lib/api/domains/writing.ts',
  apiBarrel: 'src/lib/api.ts',
  workbenchPage: 'src/pages/WritingWorkbenchPage.tsx',
  selectionLookup: 'src/components/writing/useSelectionLookup.ts',
  backendReadbackTest: path.join(repoRoot, 'main/backend/tests/unit/test_writing_keyword_card_service_unittest.py'),
  backendKeywordService: path.join(repoRoot, 'main/backend/app/services/writing/keyword_card_service.py'),
}

const failures = []

function readFile(relOrAbsPath) {
  const fullPath = path.isAbsolute(relOrAbsPath) ? relOrAbsPath : path.join(rootDir, relOrAbsPath)
  return fs.readFileSync(fullPath, 'utf8')
}

function assertIncludesAll(label, source, expected) {
  for (const item of expected) {
    if (!source.includes(item)) {
      failures.push(`${label} missing ${item}`)
    }
  }
}

const writingDomain = readFile(files.writingDomain)
const apiBarrel = readFile(files.apiBarrel)
const workbenchPage = readFile(files.workbenchPage)
const selectionLookup = readFile(files.selectionLookup)
const backendReadbackTest = readFile(files.backendReadbackTest)
const backendKeywordService = readFile(files.backendKeywordService)

assertIncludesAll('writing API typed-context helper', writingDomain, [
  "WRITING_TYPED_KNOWLEDGE_CONTEXT_VERSION = 'writing.typed_knowledge_context.v1'",
  "WRITING_TYPED_KNOWLEDGE_HANDOFF_CONTRACT_VERSION = 'typed_knowledge.writing_handoff.v1'",
  'readTypedKnowledgeWritingContextFromDocument',
  'writingTypedKnowledgeContextKey',
  'withTypedKnowledgeWritingContext',
  'typed_knowledge_context: context',
])

assertIncludesAll('writing API barrel exports', apiBarrel, [
  'readTypedKnowledgeWritingContextFromDocument',
  'writingTypedKnowledgeContextKey',
  'withTypedKnowledgeWritingContext',
  'TypedKnowledgeWritingContext',
  'TypedKnowledgeWritingHandoff',
])

assertIncludesAll('workbench consumer fetch wiring', workbenchPage, [
  'readTypedKnowledgeWritingContextFromDocument',
  'writingTypedKnowledgeContextKey',
  'withTypedKnowledgeWritingContext',
  'const writingTypedContext = useMemo',
  'const writingTypedContextKey = useMemo',
  'lookupScopeKey: writingTypedContextKey',
  "sources: ['document', 'resource', 'graph']",
])

assertIncludesAll('selection lookup scoped dedupe', selectionLookup, [
  'lookupScopeKey?: string',
  'scopedLookupKey',
  'seenLookupRef.current.get(scopedLookupKey)',
  'seenLookupRef.current.set(scopedLookupKey, Date.now())',
])

assertIncludesAll('backend deterministic card readback', backendReadbackTest, [
  'test_typed_knowledge_card_preview_and_detail_readback_after_consumer_fetch',
  'get_card_preview',
  'get_card_detail',
  'KeywordCardPreviewRequest',
  'KeywordCardDetailRequest',
  'wave16-worker5-readback',
])

assertIncludesAll('backend typed context cache source', backendKeywordService, [
  'parse_writing_knowledge_context_envelope',
  'build_keyword_card_from_typed_knowledge_handoff',
  'typed_knowledge_context_count=len(typed_knowledge_cards)',
  '"typed_knowledge_boundary_rule": "consume_typed_knowledge_handoff_as_resource_card_only"',
])

const deterministicRequest = {
  project_key: 'demo_proj',
  query: 'robotics investment',
  selection_hash: 'sel_wave16',
  sources: ['document', 'resource', 'graph'],
  context: {
    contract_version: 'writing.context_boundary.e3.v1',
    typed_knowledge_context: {
      contract_version: 'writing.typed_knowledge_context.v1',
      source: 'typed_knowledge',
      consumer: 'writing.keyword_card',
      handoffs: [
        {
          contract_version: 'typed_knowledge.writing_handoff.v1',
          knowledge_item_key: 'ki:robotics-policy',
          project_key: 'demo_proj',
          canonical_statement: 'Humanoid robotics investment is shifting toward industrial pilots.',
          primary_type_node_key: 'type:market_signal',
          topic_cluster_keys: ['topic:robotics'],
          booklet_keys: ['booklet:q2-review'],
          review_state: 'human_confirmed',
          quality_grade: 'gold',
          locale: 'en',
          evidence_refs: ['doc:robotics:42'],
          visibility_scope: 'downstream_ready',
          selection_hash: 'sel_wave16',
          selection_text: 'robotics investment',
          facets: {
            consumer_boundary: {
              consumer: 'writing.keyword_card',
              card_source_type: 'resource',
            },
          },
        },
      ],
      boundary: {
        card_source_type: 'resource',
      },
    },
  },
}

if (deterministicRequest.context.typed_knowledge_context.consumer !== 'writing.keyword_card') {
  failures.push('fixture consumer must stay writing.keyword_card')
}
if (deterministicRequest.context.typed_knowledge_context.handoffs[0].contract_version !== 'typed_knowledge.writing_handoff.v1') {
  failures.push('fixture handoff version drifted')
}
if (!deterministicRequest.sources.includes('resource')) {
  failures.push('fixture must request resource cards so typed knowledge can read back as a resource')
}

const summary = {
  status: failures.length === 0 ? 'ok' : 'failed',
  contract_version: 'writing_workbench_typed_fetch.wave16.worker5.v1',
  checked_files: Object.values(files),
  deterministic_fixture: {
    consumer: deterministicRequest.context.typed_knowledge_context.consumer,
    source_type: deterministicRequest.context.typed_knowledge_context.boundary.card_source_type,
    handoff_count: deterministicRequest.context.typed_knowledge_context.handoffs.length,
  },
  live_closure_claimed: false,
  remaining_live_conditions: [
    'public_typed_knowledge_api_route_not_implemented',
    'live_db_persistence_not_implemented',
    'persisted_typed_knowledge_cards_live_readback_not_verified',
  ],
  failures,
}

console.log(JSON.stringify(summary, null, 2))

if (failures.length > 0) {
  process.exitCode = 1
}
