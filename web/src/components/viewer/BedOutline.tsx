import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import type { ReactElement } from 'react'
import { BoxGeometry, EdgesGeometry } from 'three'
import type { LineSegments } from 'three'
import type { PrintVolume, Vec3 } from '../../api/types'
import { BED_COLOR } from '../../lib/colors'

/** Dashed print-volume box centred on `center` (model coordinates) for scale reference. */
export function BedOutline({ bed, center }: { bed: PrintVolume; center: Vec3 }): ReactElement {
  const ref = useRef<LineSegments>(null)
  const geometry = useMemo(() => new EdgesGeometry(new BoxGeometry(bed.x, bed.y, bed.z)), [bed.x, bed.y, bed.z])
  useEffect(() => () => geometry.dispose(), [geometry])
  useLayoutEffect(() => {
    ref.current?.computeLineDistances()
  }, [geometry])
  const dash = Math.max(bed.x, bed.y, bed.z) / 60
  return (
    <lineSegments ref={ref} geometry={geometry} position={center}>
      <lineDashedMaterial color={BED_COLOR} dashSize={dash} gapSize={dash * 0.6} transparent opacity={0.6} />
    </lineSegments>
  )
}
