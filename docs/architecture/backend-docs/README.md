# Backend Docs Architecture Migration Entry

> Date: 2026-05-22
> Status: Wave19 moved-file batch; shared navigation remains compatibility-bound
> Manifest: [latest-dev-docs-entry-manifest.json](../latest-dev-docs-entry-manifest.json)
> Target root: `docs/architecture/backend-docs`
> Shim: `docs/architecture/backend-docs/README.md`

This entry maps the explicit backend-docs architecture tree into the future `docs/architecture/` taxonomy. Wave19 moved the backend-docs architecture files into this target root and left the old latest-dev-docs paths as compatibility shims.

## Moved Content Batch

| Previous compatibility path | Authoritative target | Role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md](./A_ARCHITECTURE/API_CONTRACT_STANDARD.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/INGEST_ARCHITECTURE.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/INGEST_ARCHITECTURE.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/INGEST_ARCHITECTURE.md](./A_ARCHITECTURE/INGEST_ARCHITECTURE.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md](./A_ARCHITECTURE/LOTTERY_DECOUPLING_INVENTORY.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md](./A_ARCHITECTURE/NUMERIC_DATA_HOMOGENIZATION_ROADMAP.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/PHASE5_LLM_SYMBOLIZATION_MVP.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/PHASE5_LLM_SYMBOLIZATION_MVP.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/PHASE5_LLM_SYMBOLIZATION_MVP.md](./A_ARCHITECTURE/PHASE5_LLM_SYMBOLIZATION_MVP.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/RESOURCE_LIBRARY_DEFINITION.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/RESOURCE_LIBRARY_DEFINITION.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/RESOURCE_LIBRARY_DEFINITION.md](./A_ARCHITECTURE/RESOURCE_LIBRARY_DEFINITION.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md](./A_ARCHITECTURE/RESOURCE_LIBRARY_IMPLEMENTATION_PLAN.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/STRUCTURED_VS_GRAPH_ALIGNMENT.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/STRUCTURED_VS_GRAPH_ALIGNMENT.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/STRUCTURED_VS_GRAPH_ALIGNMENT.md](./A_ARCHITECTURE/STRUCTURED_VS_GRAPH_ALIGNMENT.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/UNIFIED_COLLECT_ARCHITECTURE.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/UNIFIED_COLLECT_ARCHITECTURE.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/UNIFIED_COLLECT_ARCHITECTURE.md](./A_ARCHITECTURE/UNIFIED_COLLECT_ARCHITECTURE.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/政策数据结构说明.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/政策数据结构说明.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/政策数据结构说明.md](./A_ARCHITECTURE/政策数据结构说明.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/数据库说明文档.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/数据库说明文档.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/数据库说明文档.md](./A_ARCHITECTURE/数据库说明文档.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/文档去重逻辑说明.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/文档去重逻辑说明.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/文档去重逻辑说明.md](./A_ARCHITECTURE/文档去重逻辑说明.md) | explicit backend-docs architecture file | content moved; target authoritative |
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/社交平台图谱生成标准文档.md](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/社交平台图谱生成标准文档.md) | [docs/architecture/backend-docs/A_ARCHITECTURE/社交平台图谱生成标准文档.md](./A_ARCHITECTURE/社交平台图谱生成标准文档.md) | explicit backend-docs architecture file | content moved; target authoritative |

## Compatibility Entries

| Source path | Readable compatibility entry | Target role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/backend-docs/A_ARCHITECTURE](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE) | [development/latest-dev-docs/backend-docs/A_ARCHITECTURE](../../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE) | compatibility shim tree | target authoritative files; source shims retained |

## Compatibility Rule

The moved target files are authoritative for the backend-docs architecture tree. The old latest-dev-docs files remain as compatibility shims until a supervisor-owned integration pass updates shared navigation and shared overview references.
