export { informationTopologyClient } from './client'
export { MappingStatus } from './MappingStatus'
export { classifyReference } from './referenceStatus'
export { TopologyDetail } from './TopologyDetail'
export {
  createTopologyBoundRef,
  createTopologyElement,
  createTopologyState,
  defineTopologyCreationContract,
  TOPOLOGY_STRUCTURAL_FIELDS,
} from './creationSchema'
export type {
  CreateTopologyElementInput,
  CreateTopologyStateInput,
  TopologyCreationContract,
  TopologyStructuralField,
  TopologyStructuralRole,
} from './creationSchema'
export type * from './types'
export type { ReferenceStatus } from './referenceStatus'
