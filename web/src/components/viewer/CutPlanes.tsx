import type { ReactElement } from 'react'
import { Edges } from '@react-three/drei'
import { DoubleSide } from 'three'
import type { Axis, CutPlan, Vec3 } from '../../api/types'
import { boundsCenter, boundsSize } from '../../lib/explode'
import { PLANE_COLOR } from '../../lib/colors'
import { quadExtent } from '../../lib/planes'

interface Quad {
  key: string
  position: Vec3
  rotation: Vec3
  size: [number, number]
}

/** A plane geometry lies in local XY (normal +Z); rotate it so its normal is the cut axis.
 *  Quads are centred on the plan and padded (see `quadExtent`) so thin plans still show planes. */
function quad(axis: Axis, at: number, center: Vec3, size: Vec3, i: number): Quad {
  const key = `${axis}${i}`
  const extent = quadExtent(axis, size)
  if (axis === 'x') return { key, position: [at, center[1], center[2]], rotation: [0, Math.PI / 2, 0], size: extent }
  if (axis === 'y') return { key, position: [center[0], at, center[2]], rotation: [-Math.PI / 2, 0, 0], size: extent }
  return { key, position: [center[0], center[1], at], rotation: [0, 0, 0], size: extent }
}

export function CutPlanes({ plan, visible }: { plan: CutPlan; visible: boolean }): ReactElement {
  const center = boundsCenter(plan.bounds)
  const size = boundsSize(plan.bounds)
  const axes: Axis[] = ['x', 'y', 'z']
  const quads = axes.flatMap((a) => (plan.cuts[a] ?? []).map((p, i) => quad(a, p, center, size, i)))
  return (
    <group visible={visible}>
      {quads.map((q) => (
        <mesh key={q.key} position={q.position} rotation={q.rotation}>
          <planeGeometry args={q.size} />
          <meshBasicMaterial color={PLANE_COLOR} transparent opacity={0.18} side={DoubleSide} depthWrite={false} />
          <Edges color={PLANE_COLOR} />
        </mesh>
      ))}
    </group>
  )
}
