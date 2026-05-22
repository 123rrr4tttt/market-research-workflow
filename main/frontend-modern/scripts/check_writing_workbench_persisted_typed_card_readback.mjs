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
  evidenceDoc: path.join(
    repoRoot,
    'development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-writing-workbench-evolution/09_wave17-worker6-persisted-typed-card-ui-readback-2026-05-22.md',
  ),
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
const evidenceDoc = readFile(files.evidenceDoc)

assertIncludesAll('persisted typed-card request helper', writingDomain, [
  'buildPersistedTypedKnowledgeKeywordCardRequest',
  "document: Pick<WritingDocument, 'metadata_json'> | null | undefined",
  'const typedContext = readTypedKnowledgeWritingContextFromDocument(document)',
  "sources = ['document', 'resource', 'graph']",
  'withTypedKnowledgeWritingContext',
])

assertIncludesAll('API barrel export', apiBarrel, [
  'buildPersistedTypedKnowledgeKeywordCardRequest',
])

assertIncludesAll('workbench persisted UI consumer path', workbenchPage, [
  'buildPersistedTypedKnowledgeKeywordCardRequest',
  'lookupScopeKey: writingTypedContextKey',
  'document: documentDetailQuery.data',
  'getWritingKeywordCards(',
])

assertIncludesAll('scoped selection readback trigger', selectionLookup, [
  'lookupScopeKey?: string',
  'scopedLookupKey',
  'seenLookupRef.current.get(scopedLookupKey)',
  'seenLookupRef.current.set(scopedLookupKey, Date.now())',
])

assertIncludesAll('backend preview/detail readback test remains wired', backendReadbackTest, [
  'test_typed_knowledge_card_preview_and_detail_readback_after_consumer_fetch',
  'get_card_preview',
  'get_card_detail',
  'self.assertEqual(detail.provenance["raw_keys"], ["typed_knowledge_context"])',
])

assertIncludesAll('Wave17 evidence doc', evidenceDoc, [
  'Wave17 Worker6 Persisted Typed-Card UI Readback',
  'buildPersistedTypedKnowledgeKeywordCardRequest',
  'No live browser/UI persisted readback was claimed',
  'persisted_typed_knowledge_cards_live_readback_not_verified',
])

const deterministicPersistedDocument = {
  metadata_json: {
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
          selection_hash: 'sel_wave17',
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
        boundary_rule: 'consume_typed_knowledge_handoff_as_resource_card_only',
        card_source_type: 'resource',
      },
    },
  },
}

const typedContext = deterministicPersistedDocument.metadata_json.typed_knowledge_context
if (typedContext.consumer !== 'writing.keyword_card') failures.push('fixture consumer drifted')
if (typedContext.boundary.card_source_type !== 'resource') failures.push('fixture source type drifted')
if (typedContext.handoffs.length !== 1) failures.push('fixture must have exactly one handoff')
if (typedContext.handoffs[0].visibility_scope !== 'downstream_ready') failures.push('fixture must stay downstream_ready')

const summary = {
  status: failures.length === 0 ? 'ok' : 'failed',
  contract_version: 'writing_workbench_persisted_typed_card_readback.wave17.worker6.v1',
  checked_files: Object.values(files),
  deterministic_fixture: {
    persisted_document_metadata: true,
    consumer: typedContext.consumer,
    card_source_type: typedContext.boundary.card_source_type,
    handoff_count: typedContext.handoffs.length,
  },
  live_persisted_ui_closure_claimed: false,
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
