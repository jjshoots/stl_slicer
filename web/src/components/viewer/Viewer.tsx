import { Suspense, useEffect } from 'react'
import type { ReactElement } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { Grid, OrbitControls } from '@react-three/drei'
import type { CutPlan, PieceInfo, PrintVolume, Vec3 } from '../../api/types'
import { boundsCenter, boundsSize } from '../../lib/explode'
import { BedOutline } from './BedOutline'
import { CellBoxes } from './CellBoxes'
import { CutPlanes } from './CutPlanes'
import { ModelMesh } from './ModelMesh'
import { PiecesScene } from './PiecesScene'

export interface ViewerProps {
  modelUrl?: string
  piecesUrl?: string
  pieces?: PieceInfo[]
  plan?: CutPlan
  bed: PrintVolume
  explode: number
  showPlanes: boolean
  hidden: Set<string>
  selected?: string
  onSelect(id: string): void
}

interface Framing {
  center: Vec3 // model-frame centre of the framed box
  minZ: number
  height: number
  radius: number
}

/** Frame the plan bounds, or a bed-sized box standing on the origin when there is no plan. */
function framing(plan: CutPlan | undefined, bed: PrintVolume): Framing {
  const b = plan?.bounds ?? { min: [-bed.x / 2, -bed.y / 2, 0], max: [bed.x / 2, bed.y / 2, bed.z] }
  const s = boundsSize(b)
  return { center: boundsCenter(b), minZ: b.min[2], height: s[2], radius: Math.max(Math.hypot(...s) / 2, 1) }
}

/** Reposition the camera whenever the framed radius changes (Canvas `camera` only applies on mount). */
function CameraRig({ radius }: { radius: number }): null {
  const camera = useThree((s) => s.camera)
  useEffect(() => {
    camera.position.set(radius * 1.6, radius * 1.2, radius * 1.6)
    camera.near = radius / 100
    camera.far = radius * 20
    camera.updateProjectionMatrix()
  }, [camera, radius])
  return null
}

export function Viewer(props: ViewerProps): ReactElement {
  const { modelUrl, piecesUrl, pieces, plan, bed, explode, showPlanes, hidden, selected, onSelect } = props
  // Cheap to recompute each render; CameraRig/OrbitControls only react to the derived numbers,
  // so live plan previews with unchanged bounds don't reset the camera.
  const f = framing(plan, bed)
  const r = f.radius
  const empty = !modelUrl && !piecesUrl

  return (
    <div className="viewer-pane">
      <Canvas camera={{ position: [r * 1.6, r * 1.2, r * 1.6], near: r / 100, far: r * 20, fov: 45 }}>
        <color attach="background" args={['#121417']} />
        <ambientLight intensity={0.35} />
        <hemisphereLight args={['#dfe8f0', '#20242a', 0.6]} />
        <directionalLight position={[r * 2, r * 3, r * 1.5]} intensity={1.6} />
        <CameraRig radius={r} />
        <Grid
          infiniteGrid
          cellSize={10}
          sectionSize={100}
          cellColor="#2a2f36"
          sectionColor="#3a414a"
          cellThickness={0.6}
          sectionThickness={1}
          fadeDistance={r * 10}
        />
        <OrbitControls makeDefault target={[0, f.height / 2, 0]} />
        {/* Model frame is Z-up (print bed); rotate so model +Z = three +Y, then centre in XY with the bottom on the grid. */}
        <group rotation={[-Math.PI / 2, 0, 0]}>
          <group position={[-f.center[0], -f.center[1], -f.minZ]}>
            <Suspense fallback={null}>
              {modelUrl && <ModelMesh key={modelUrl} url={modelUrl} visible={!piecesUrl} />}
              {piecesUrl && (
                <PiecesScene
                  key={piecesUrl}
                  url={piecesUrl}
                  pieces={pieces}
                  plan={plan}
                  explode={explode}
                  hidden={hidden}
                  selected={selected}
                  onSelect={onSelect}
                />
              )}
            </Suspense>
            {plan && <CutPlanes plan={plan} visible={showPlanes} />}
            {plan && <CellBoxes plan={plan} visible={showPlanes} />}
            {!empty && <BedOutline bed={bed} center={f.center} />}
          </group>
        </group>
      </Canvas>
      {empty && <div className="viewer-empty">Upload a model to begin</div>}
    </div>
  )
}
