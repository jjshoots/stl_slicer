import { useEffect } from 'react'
import { planModel } from '../api/client'
import { useDataStore } from '../store/data'

const DEBOUNCE_MS = 250

/** Keeps `plan` in sync with `model` + `spec`: debounced, aborting superseded requests. */
export function usePlanPreview(): void {
  const model = useDataStore((s) => s.model)
  const spec = useDataStore((s) => s.spec)

  useEffect(() => {
    if (model === null) return
    const ctrl = new AbortController()
    const timer = setTimeout(() => {
      planModel(model.model_id, spec, ctrl.signal).then(
        (plan) => {
          if (!ctrl.signal.aborted) useDataStore.getState().setPlan(plan, null)
        },
        (err: unknown) => {
          if (ctrl.signal.aborted) return
          useDataStore.getState().setPlan(null, err instanceof Error ? err.message : String(err))
        },
      )
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
  }, [model, spec])
}
