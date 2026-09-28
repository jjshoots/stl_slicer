import { useEffect, useMemo } from 'react'
import type { ReactElement } from 'react'
import { useGLTF } from '@react-three/drei'
import type { ThreeEvent } from '@react-three/fiber'
import { Matrix4 } from 'three'
import type { BufferGeometry, Mesh, Object3D } from 'three'
import type { CutPlan, PieceInfo, Vec3 } from '../../api/types'
import { explodeOffset } from '../../lib/explode'
import { SELECTED_EMISSIVE, pieceColor } from '../../lib/colors'

interface PieceMesh {
  id: string
  geometry: BufferGeometry
}

/** Every Mesh in the scene, keyed by the first non-empty name walking up from the mesh (= piece_id). */
function collectPieceMeshes(scene: Object3D): PieceMesh[] {
  const out: PieceMesh[] = []
  const identity = new Matrix4()
  scene.updateMatrixWorld(true)
  scene.traverse((o) => {
    if (!(o as Mesh).isMesh) return
    const mesh = o as Mesh
    let node: Object3D | null = mesh
    while (node && !node.name) node = node.parent
    const id = node?.name || mesh.uuid
    // Bake any node transform so the geometry is in the model frame.
    const geometry = mesh.matrixWorld.equals(identity) ? mesh.geometry : mesh.geometry.clone().applyMatrix4(mesh.matrixWorld)
    out.push({ id, geometry })
  })
  return out
}

interface PiecesSceneProps {
  url: string
  pieces?: PieceInfo[]
  plan?: CutPlan
  explode: number
  hidden: Set<string>
  selected?: string
  onSelect(id: string): void
}

export function PiecesScene({ url, pieces, plan, explode, hidden, selected, onSelect }: PiecesSceneProps): ReactElement {
  const { scene } = useGLTF(url)
  const items = useMemo(
    () =>
      collectPieceMeshes(scene).map((m, fileIndex) => {
        const i = pieces?.findIndex((p) => p.piece_id === m.id) ?? -1
        return { ...m, index: i >= 0 ? i : fileIndex, cell: i >= 0 ? pieces?.[i].cell : undefined }
      }),
    [scene, pieces],
  )
  useEffect(() => () => void (document.body.style.cursor = ''), [])

  const hover = (on: boolean) => (e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation()
    document.body.style.cursor = on ? 'pointer' : ''
  }

  return (
    <group>
      {items
        .filter((p) => !hidden.has(p.id))
        .map((p) => {
          const offset: Vec3 = p.cell && plan ? explodeOffset(p.cell, plan, explode) : [0, 0, 0]
          const isSelected = p.id === selected
          return (
            <mesh
              key={p.id}
              geometry={p.geometry}
              position={offset}
              onClick={(e) => {
                e.stopPropagation()
                onSelect(p.id)
              }}
              onPointerOver={hover(true)}
              onPointerOut={hover(false)}
            >
              <meshStandardMaterial
                color={pieceColor(p.index)}
                roughness={0.55}
                metalness={0.05}
                emissive={isSelected ? SELECTED_EMISSIVE : '#000000'}
                emissiveIntensity={isSelected ? 0.35 : 0}
              />
            </mesh>
          )
        })}
    </group>
  )
}
