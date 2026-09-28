import { useMemo } from 'react'
import type { ReactElement } from 'react'
import { useGLTF } from '@react-three/drei'
import { FrontSide, MeshStandardMaterial } from 'three'
import type { Mesh } from 'three'

export function ModelMesh({ url, visible }: { url: string; visible: boolean }): ReactElement {
  const { scene } = useGLTF(url)
  const object = useMemo(() => {
    const material = new MeshStandardMaterial({ color: '#b8c0c8', roughness: 0.6, metalness: 0.05, side: FrontSide })
    scene.traverse((o) => {
      if ((o as Mesh).isMesh) (o as Mesh).material = material
    })
    return scene
  }, [scene])
  return <primitive object={object} visible={visible} />
}
