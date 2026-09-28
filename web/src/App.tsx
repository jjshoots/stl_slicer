import type { ReactElement } from 'react'
import { downloadZipUrl, modelMeshUrl, piecesGlbUrl, setOnModelGone } from './api/client'
import { AppShell } from './components/layout/AppShell'
import { DownloadBar } from './components/pieces/DownloadBar'
import { PiecesList } from './components/pieces/PiecesList'
import { SpecPanel } from './components/spec/SpecPanel'
import { Viewer } from './components/viewer/Viewer'
import { useModelUpload } from './hooks/useModelUpload'
import { usePlanPreview } from './hooks/usePlanPreview'
import { usePresets } from './hooks/usePresets'
import { useSliceJob } from './hooks/useSliceJob'
import { boundsSize } from './lib/explode'
import { useDataStore } from './store/data'
import { useViewStore } from './store/view'

setOnModelGone(() => useDataStore.getState().reset())

export function App(): ReactElement {
  const model = useDataStore((s) => s.model)
  const spec = useDataStore((s) => s.spec)
  const plan = useDataStore((s) => s.plan)
  const job = useDataStore((s) => s.job)
  const result = useDataStore((s) => s.result)
  const uploading = useDataStore((s) => s.uploading)
  const uploadError = useDataStore((s) => s.uploadError)

  const explode = useViewStore((s) => s.explode)
  const showPlanes = useViewStore((s) => s.showPlanes)
  const hidden = useViewStore((s) => s.hidden)
  const selected = useViewStore((s) => s.selected)
  const setExplode = useViewStore((s) => s.setExplode)
  const setShowPlanes = useViewStore((s) => s.setShowPlanes)
  const toggleHidden = useViewStore((s) => s.toggleHidden)
  const select = useViewStore((s) => s.select)

  usePlanPreview()
  const presets = usePresets()
  const { upload } = useModelUpload()
  const { submit, cancel } = useSliceJob()

  return (
    <AppShell
      sidebar={
        <>
          <SpecPanel
            presets={presets}
            uploading={uploading}
            uploadError={uploadError}
            onUpload={(file, scale) => {
              void upload(file, scale)
            }}
          />
          <PiecesList
            pieces={result?.pieces ?? []}
            selected={selected}
            hidden={hidden}
            warnings={result?.warnings ?? []}
            onSelect={select}
            onToggleHidden={toggleHidden}
          />
        </>
      }
      viewer={
        <Viewer
          modelUrl={model ? modelMeshUrl(model.model_id) : undefined}
          piecesUrl={result ? piecesGlbUrl(result.job_id) : undefined}
          pieces={result?.pieces}
          plan={result?.plan ?? plan ?? undefined}
          bed={spec.print_volume}
          explode={explode}
          showPlanes={showPlanes}
          hidden={hidden}
          selected={selected ?? undefined}
          onSelect={(id) => select(selected === id ? null : id)}
          modelSize={model ? boundsSize(model.bounds) : undefined}
          pieceCount={result?.stats.piece_count}
        />
      }
      footer={
        <DownloadBar
          explode={explode}
          onExplode={setExplode}
          showPlanes={showPlanes}
          onShowPlanes={setShowPlanes}
          job={job}
          canSlice={model !== null && plan !== null}
          onSlice={() => {
            void submit()
          }}
          onCancel={() => {
            void cancel()
          }}
          downloadUrl={result ? downloadZipUrl(result.job_id) : null}
        />
      }
    />
  )
}
