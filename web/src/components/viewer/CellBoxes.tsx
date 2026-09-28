import { useEffect, useMemo } from 'react'
import type { ReactElement } from 'react'
import { BoxGeometry, EdgesGeometry } from 'three'
import type { CutPlan } from '../../api/types'
import { boundsCenter, boundsSize, cellKey } from '../../lib/explode'
import { CELL_COLOR } from '../../lib/colors'

export function CellBoxes({ plan, visible }: { plan: CutPlan; visible: boolean }): ReactElement {
  // One unit-cube outline shared by all cells, scaled to each cell's size.
  const unit = useMemo(() => new EdgesGeometry(new BoxGeometry(1, 1, 1)), [])
  useEffect(() => () => unit.dispose(), [unit])
  return (
    <group visible={visible}>
      {plan.cells.map((c) => (
        <lineSegments key={cellKey(c.index)} geometry={unit} position={boundsCenter(c.bounds)} scale={boundsSize(c.bounds)}>
          <lineBasicMaterial color={CELL_COLOR} transparent opacity={0.35} depthWrite={false} />
        </lineSegments>
      ))}
    </group>
  )
}
