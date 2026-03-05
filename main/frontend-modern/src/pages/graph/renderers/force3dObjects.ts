import * as THREE from 'three'

export type ForceNodeObjectStyle = {
  size: number
  color: string
  opacity: number
  rawSymbol: string
  graphSymbol: 'circle' | 'rect' | 'roundRect' | 'triangle' | 'diamond' | 'pin' | 'arrow'
}

type ForceVisualApplier = (object: THREE.Object3D, selected: boolean, dimmed: boolean) => void

type ForceNodeObjectFactoryParams = {
  cache: Map<string, THREE.Object3D>
  id: string
  style: ForceNodeObjectStyle
  isSelected: boolean
  applyVisualState: ForceVisualApplier
}

function forEachMesh(object: THREE.Object3D, visit: (mesh: THREE.Mesh) => void) {
  if (object instanceof THREE.Mesh) {
    visit(object)
    return
  }
  object.traverse((child) => {
    if (child instanceof THREE.Mesh) visit(child)
  })
}


function refreshObjectScale(object: THREE.Object3D, size: number) {
  const baseSize = Number((object.userData as { __graphNodeBaseSize?: unknown })?.__graphNodeBaseSize || size)
  const ratio = Math.max(0.2, size / Math.max(0.001, baseSize))
  object.scale.set(ratio, ratio, ratio)
  if (object.userData && typeof object.userData === 'object') {
    delete object.userData.__graphNodeBaseScale
    delete object.userData.__graphNodeSelected
    delete object.userData.__graphNodeDimmed
  }
}

function refreshObjectMaterial(object: THREE.Object3D, style: ForceNodeObjectStyle) {
  const isEmpty = style.rawSymbol.startsWith('empty')
  const useTransparent = style.opacity < 0.985
  forEachMesh(object, (mesh) => {
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material]
    materials.forEach((mat) => {
      if (!mat) return
      const isEmptyCore = Boolean((mesh.userData as { __graphEmptyCore?: unknown })?.__graphEmptyCore)
      if ('color' in mat && (mat as THREE.MeshBasicMaterial | THREE.MeshLambertMaterial).color) {
        ;(mat as THREE.MeshBasicMaterial | THREE.MeshLambertMaterial).color.set(
          isEmpty ? (isEmptyCore ? '#ffffff' : style.color) : style.color,
        )
      }
      if ('transparent' in mat) {
        ;(mat as THREE.MeshBasicMaterial | THREE.MeshLambertMaterial).transparent = useTransparent
      }
      if ('opacity' in mat) {
        ;(mat as THREE.MeshBasicMaterial | THREE.MeshLambertMaterial).opacity = useTransparent ? style.opacity : 1
      }
      if ('depthWrite' in mat) {
        ;(mat as THREE.MeshBasicMaterial | THREE.MeshLambertMaterial).depthWrite = !useTransparent
      }
      if ('depthTest' in mat) {
        ;(mat as THREE.MeshBasicMaterial | THREE.MeshLambertMaterial).depthTest = true
      }
      mat.needsUpdate = true
    })
  })
}

function buildForceNodeObject(style: ForceNodeObjectStyle): THREE.Object3D {
  const isEmpty = style.rawSymbol.startsWith('empty')
  const useTransparent = style.opacity < 0.985
  const material = new THREE.MeshLambertMaterial({
    color: style.color,
    transparent: useTransparent,
    opacity: useTransparent ? style.opacity : 1,
    wireframe: false,
    side: THREE.FrontSide,
    depthTest: true,
    depthWrite: !useTransparent,
    emissive: new THREE.Color('#000000'),
    emissiveIntensity: 0,
  })

  const buildPrimitiveByStyle = (size: number, meshMaterial: THREE.MeshLambertMaterial) => {
    if (style.rawSymbol === 'convexStar') {
      return new THREE.Mesh(new THREE.IcosahedronGeometry(size * 1.16, 0), meshMaterial)
    }
    if (style.graphSymbol === 'rect' || style.graphSymbol === 'roundRect') {
      return new THREE.Mesh(new THREE.BoxGeometry(size * 2.2, size * 1.35, size * 1.35), meshMaterial)
    }
    if (style.graphSymbol === 'diamond') {
      return new THREE.Mesh(new THREE.OctahedronGeometry(size * 1.28), meshMaterial)
    }
    if (style.graphSymbol === 'triangle') {
      return new THREE.Mesh(new THREE.ConeGeometry(size * 1.2, size * 2.3, isEmpty ? 12 : 3), meshMaterial)
    }
    if (style.graphSymbol === 'pin') {
      const group = new THREE.Group()
      const head = new THREE.Mesh(new THREE.SphereGeometry(size * 0.86, 14, 14), meshMaterial)
      const tail = new THREE.Mesh(new THREE.ConeGeometry(size * 0.6, size * 1.65, 8), meshMaterial)
      tail.position.set(0, -size * 1.16, 0)
      group.add(head)
      group.add(tail)
      return group
    }
    if (style.graphSymbol === 'arrow') {
      const group = new THREE.Group()
      const body = new THREE.Mesh(new THREE.CylinderGeometry(size * 0.2, size * 0.2, size * 1.7, 10), meshMaterial)
      const head = new THREE.Mesh(new THREE.ConeGeometry(size * 0.45, size * 0.95, 12), meshMaterial)
      body.rotation.z = Math.PI / 2
      head.rotation.z = -Math.PI / 2
      head.position.set(size * 1.12, 0, 0)
      group.add(body)
      group.add(head)
      return group
    }
    return new THREE.Mesh(new THREE.SphereGeometry(size * 1.03, 14, 14), meshMaterial)
  }

  const size = style.size
  let object: THREE.Object3D
  if (isEmpty) {
    const outer = buildPrimitiveByStyle(size, material)
    const borderThickness = Math.max(0.5, Math.min(2.2, size * 0.2))
    const innerSize = Math.max(size * 0.56, size - borderThickness)
    const innerMaterial = new THREE.MeshLambertMaterial({
      color: '#ffffff',
      transparent: useTransparent,
      opacity: useTransparent ? style.opacity : 1,
      wireframe: false,
      side: THREE.FrontSide,
      depthTest: true,
      depthWrite: !useTransparent,
      emissive: new THREE.Color('#000000'),
      emissiveIntensity: 0,
    })
    const inner = buildPrimitiveByStyle(innerSize, innerMaterial)
    forEachMesh(inner, (mesh) => {
      mesh.userData = {
        ...(mesh.userData || {}),
        __graphEmptyCore: true,
      }
    })
    const group = new THREE.Group()
    group.add(outer)
    group.add(inner)
    object = group
  } else {
    object = buildPrimitiveByStyle(size, material)
  }

  forEachMesh(object, (mesh) => {
    mesh.frustumCulled = false
  })
  object.userData = {
    ...(object.userData || {}),
    __graphNodeIsEmpty: isEmpty,
    __graphNodeBaseSize: size,
  }
  return object
}

export function getOrCreateForceNodeObject(params: ForceNodeObjectFactoryParams) {
  const { cache, id, style, isSelected, applyVisualState } = params
  void cache
  const stableSizeBucket = Math.round(style.size * 2) / 2
  // Permanent stability path:
  // build node object every render call and do not reuse object references.
  // force-graph's internal lifecycle can detach/reparent objects unpredictably
  // when external caches hand back stale instances.
  const object = buildForceNodeObject({ ...style, size: stableSizeBucket })
  refreshObjectScale(object, stableSizeBucket)
  refreshObjectMaterial(object, style)
  object.userData = {
    ...(object.userData || {}),
    __graphNodeObject: true,
    __graphNodeId: id,
    __graphNodeIsEmpty: style.rawSymbol.startsWith('empty'),
  }
  applyVisualState(object, isSelected, false)
  return object
}

export function pruneForceNodeObjectCache(cache: Map<string, THREE.Object3D>, activeNodeIds: Set<string>) {
  // Cache pruning is intentionally a no-op after removing object reuse path.
  void cache
  void activeNodeIds
}

export function linkEnds(link: unknown) {
  const payload = link as { source?: string | { id?: string }; target?: string | { id?: string } }
  const source = typeof payload.source === 'string' ? payload.source : String(payload.source?.id || '')
  const target = typeof payload.target === 'string' ? payload.target : String(payload.target?.id || '')
  return { source, target }
}
