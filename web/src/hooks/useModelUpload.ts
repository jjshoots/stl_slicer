import { useCallback } from 'react'
import { uploadModel } from '../api/client'
import { useDataStore } from '../store/data'
import { useViewStore } from '../store/view'

export function useModelUpload(): { upload(file: File, scale: number): Promise<void> } {
  const upload = useCallback(async (file: File, scale: number) => {
    const data = useDataStore.getState()
    data.setUploading(true)
    data.setUploadError(null)
    try {
      const asset = await uploadModel(file, scale)
      useDataStore.getState().setModel(asset)
      useViewStore.getState().resetPieces()
    } catch (err) {
      useDataStore.getState().setUploadError(err instanceof Error ? err.message : String(err))
    } finally {
      useDataStore.getState().setUploading(false)
    }
  }, [])
  return { upload }
}
