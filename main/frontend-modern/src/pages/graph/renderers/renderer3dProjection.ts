import type { RenderApplyResult, RenderNode } from './types'

export const RENDERER_PROJECTION_3D_CAPABILITIES = {
  supportsForceControl: false,
  supportsProjectionControls: true,
} as const

function hashText(input: string) {
  let h = 0
  for (let i = 0; i < input.length; i += 1) h = (h * 31 + input.charCodeAt(i)) >>> 0
  return h
}

function projectPoint3D(
  x: number,
  y: number,
  z: number,
  rotXDeg: number,
  rotYDeg: number,
  rotZDeg: number,
) {
  const rx = (rotXDeg * Math.PI) / 180
  const ry = (rotYDeg * Math.PI) / 180
  const rz = (rotZDeg * Math.PI) / 180
  const cx = Math.cos(rx)
  const sx = Math.sin(rx)
  const cy = Math.cos(ry)
  const sy = Math.sin(ry)
  const cz = Math.cos(rz)
  const sz = Math.sin(rz)

  const r00 = cz * cy
  const r01 = cz * sy * sx - sz * cx
  const r02 = cz * sy * cx + sz * sx
  const r10 = sz * cy
  const r11 = sz * sy * sx + cz * cx
  const r12 = sz * sy * cx - cz * sx
  const r20 = -sy
  const r21 = cy * sx
  const r22 = cy * cx

  return {
    x: r00 * x + r01 * y + r02 * z,
    y: r10 * x + r11 * y + r12 * z,
    z: r20 * x + r21 * y + r22 * z,
  }
}

type QuaternionLike = { x: number; y: number; z: number; w: number }

function normalizeQuat(q: QuaternionLike): QuaternionLike {
  const len = Math.sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w) || 1
  return { x: q.x / len, y: q.y / len, z: q.z / len, w: q.w / len }
}

function rotatePointByQuaternion(point: Point3D, q: QuaternionLike): Point3D {
  const nq = normalizeQuat(q)
  const qx = nq.x
  const qy = nq.y
  const qz = nq.z
  const qw = nq.w
  const px = point.x
  const py = point.y
  const pz = point.z

  const tx = 2 * (qy * pz - qz * py)
  const ty = 2 * (qz * px - qx * pz)
  const tz = 2 * (qx * py - qy * px)

  return {
    x: px + qw * tx + (qy * tz - qz * ty),
    y: py + qw * ty + (qz * tx - qx * tz),
    z: pz + qw * tz + (qx * ty - qy * tx),
  }
}

export type Point3D = { x: number; y: number; z: number }
export type Projection3DPhysicsState = {
  positions: Record<string, Point3D>
  velocities: Record<string, Point3D>
}

export type Projection3DEdge = { from: string; to: string }

type Projection3DApplyResult = {
  render: RenderApplyResult
  physics: Projection3DPhysicsState
}

function seedPoint3D(key: string): Point3D {
  return {
    x: (hashText(`${key}:x3`) % 760) - 380,
    y: (hashText(`${key}:y3`) % 560) - 280,
    z: (hashText(`${key}:z3`) % 760) - 380,
  }
}

function solveForce3D(
  nodeKeys: string[],
  edges: Projection3DEdge[],
  previous: Record<string, Point3D>,
  previousVelocity: Record<string, Point3D>,
  repulsionPercent: number,
): Projection3DPhysicsState {
  const n = nodeKeys.length
  if (!n) return { positions: {}, velocities: {} }
  const nextPositions: Record<string, Point3D> = {}
  const nextVelocities: Record<string, Point3D> = {}
  const points = nodeKeys.map((key) => {
    const prev = previous[key]
    return prev ? { ...prev } : seedPoint3D(key)
  })
  const velocities = nodeKeys.map((key) => {
    const prev = previousVelocity[key]
    return prev ? { ...prev } : { x: 0, y: 0, z: 0 }
  })
  const keyIndex = new Map(nodeKeys.map((key, i) => [key, i]))
  const edgePairs = edges
    .map((e) => {
      const a = keyIndex.get(e.from)
      const b = keyIndex.get(e.to)
      if (a == null || b == null || a === b) return null
      return [a, b] as const
    })
    .filter((x): x is readonly [number, number] => Boolean(x))

  // Recenter initial state once before force iterations.
  let initCx = 0
  let initCy = 0
  let initCz = 0
  for (let i = 0; i < n; i += 1) {
    initCx += points[i].x
    initCy += points[i].y
    initCz += points[i].z
  }
  initCx /= n
  initCy /= n
  initCz /= n
  for (let i = 0; i < n; i += 1) {
    points[i].x -= initCx
    points[i].y -= initCy
    points[i].z -= initCz
  }

  const iterations = 6
  const repulsionRatio = Math.max(0, Math.min(40, repulsionPercent / 10))
  const rNorm = repulsionRatio / 40
  const repulsionK = 220 + 2800 * Math.pow(rNorm, 2.2)
  const edgeRestLen = 140 + 220 * rNorm
  const edgeSpringK = 0.0022 + 0.0016 * (1 - rNorm)
  const edgeDamping = 0.06 + 0.06 * (1 - rNorm)
  const velocityDecay = 0.14
  let alpha = 0.9
  const alphaDecay = 0.78
  const maxSpeed = 16 + 14 * rNorm

  for (let iter = 0; iter < iterations; iter += 1) {
    const fx = new Array<number>(n).fill(0)
    const fy = new Array<number>(n).fill(0)
    const fz = new Array<number>(n).fill(0)

    for (let i = 0; i < n; i += 1) {
      const pi = points[i]
      for (let j = i + 1; j < n; j += 1) {
        const pj = points[j]
        const dx = pi.x - pj.x
        const dy = pi.y - pj.y
        const dz = pi.z - pj.z
        const dist2 = dx * dx + dy * dy + dz * dz + 36
        const dist = Math.sqrt(dist2)
        const inv = 1 / dist
        const force = repulsionK / dist2
        const rx = dx * inv * force
        const ry = dy * inv * force
        const rz = dz * inv * force
        fx[i] += rx; fy[i] += ry; fz[i] += rz
        fx[j] -= rx; fy[j] -= ry; fz[j] -= rz
      }
    }

    edgePairs.forEach(([a, b]) => {
      const pa = points[a]
      const pb = points[b]
      const dx = pb.x - pa.x
      const dy = pb.y - pa.y
      const dz = pb.z - pa.z
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz + 1e-6)
      const pull = (dist - edgeRestLen) * edgeSpringK
      const sx = (dx / dist) * pull
      const sy = (dy / dist) * pull
      const sz = (dz / dist) * pull
      fx[a] += sx; fy[a] += sy; fz[a] += sz
      fx[b] -= sx; fy[b] -= sy; fz[b] -= sz

      // Symmetric damping along edge direction to dissipate relative motion only.
      const dvx = velocities[b].x - velocities[a].x
      const dvy = velocities[b].y - velocities[a].y
      const dvz = velocities[b].z - velocities[a].z
      const nx = dx / dist
      const ny = dy / dist
      const nz = dz / dist
      const relSpeed = dvx * nx + dvy * ny + dvz * nz
      const damp = relSpeed * edgeDamping
      const dxDamp = nx * damp
      const dyDamp = ny * damp
      const dzDamp = nz * damp
      fx[a] += dxDamp; fy[a] += dyDamp; fz[a] += dzDamp
      fx[b] -= dxDamp; fy[b] -= dyDamp; fz[b] -= dzDamp
    })

    for (let i = 0; i < n; i += 1) {
      velocities[i].x = velocities[i].x * (1 - velocityDecay) + fx[i] * alpha
      velocities[i].y = velocities[i].y * (1 - velocityDecay) + fy[i] * alpha
      velocities[i].z = velocities[i].z * (1 - velocityDecay) + fz[i] * alpha
      const speed = Math.sqrt(velocities[i].x ** 2 + velocities[i].y ** 2 + velocities[i].z ** 2)
      if (speed > maxSpeed) {
        const sv = maxSpeed / speed
        velocities[i].x *= sv
        velocities[i].y *= sv
        velocities[i].z *= sv
      }
    }

    // Remove net momentum each iteration to prevent whole-system drift.
    let mvx = 0
    let mvy = 0
    let mvz = 0
    for (let i = 0; i < n; i += 1) {
      mvx += velocities[i].x
      mvy += velocities[i].y
      mvz += velocities[i].z
    }
    mvx /= n
    mvy /= n
    mvz /= n
    for (let i = 0; i < n; i += 1) {
      velocities[i].x -= mvx
      velocities[i].y -= mvy
      velocities[i].z -= mvz
    }

    for (let i = 0; i < n; i += 1) {
      points[i].x += velocities[i].x
      points[i].y += velocities[i].y
      points[i].z += velocities[i].z
    }
    alpha *= alphaDecay
  }

  let cx = 0
  let cy = 0
  let cz = 0
  for (let i = 0; i < n; i += 1) {
    cx += points[i].x
    cy += points[i].y
    cz += points[i].z
  }
  cx /= n
  cy /= n
  cz /= n
  for (let i = 0; i < n; i += 1) {
    points[i].x -= cx
    points[i].y -= cy
    points[i].z -= cz
  }

  nodeKeys.forEach((key, i) => {
    nextPositions[key] = points[i]
    nextVelocities[key] = velocities[i]
  })
  return { positions: nextPositions, velocities: nextVelocities }
}

export function applyRendererProjection3D(
  nodes: RenderNode[],
  edges: Projection3DEdge[],
  physicsState: Projection3DPhysicsState,
  options?: {
    rotateXDeg?: number
    rotateYDeg?: number
    rotateZDeg?: number
    repulsionPercent?: number
    interactionQuat?: QuaternionLike
  },
): Projection3DApplyResult {
  const rotX = options?.rotateXDeg ?? 12
  const rotY = options?.rotateYDeg ?? 18
  const rotZ = options?.rotateZDeg ?? 0
  const repulsionPercent = options?.repulsionPercent ?? 100
  const interactionQuat = options?.interactionQuat
  const nodeKeys = nodes.map((node) => String(node.id))
  const solved = solveForce3D(
    nodeKeys,
    edges,
    physicsState.positions,
    physicsState.velocities,
    repulsionPercent,
  )
  const projectedNodes = nodes.map((node) => {
    const p3 = solved.positions[String(node.id)] || seedPoint3D(String(node.id))
    const eulerRotated = projectPoint3D(p3.x, p3.y, p3.z, rotX, rotY, rotZ)
    const rotated = interactionQuat ? rotatePointByQuaternion(eulerRotated, interactionQuat) : eulerRotated
    return {
      ...node,
      x: rotated.x,
      y: rotated.y,
    }
  })

  // Auto normalization:
  // recenter projected centroid to origin only.
  if (projectedNodes.length) {
    let sx = 0
    let sy = 0
    projectedNodes.forEach((node) => {
      sx += Number(node.x || 0)
      sy += Number(node.y || 0)
    })
    const cx = sx / projectedNodes.length
    const cy = sy / projectedNodes.length
    projectedNodes.forEach((node) => {
      node.x = Number(node.x || 0) - cx
      node.y = Number(node.y || 0) - cy
    })
  }

  return {
    render: {
      nodes: projectedNodes,
      series: {
        layout: 'none',
        animation: false,
        animationDurationUpdate: 0,
        animationEasingUpdate: 'linear',
      },
      cacheNodePositions: false,
      capabilities: RENDERER_PROJECTION_3D_CAPABILITIES,
    },
    physics: solved,
  }
}
