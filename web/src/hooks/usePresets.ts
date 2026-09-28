import { useEffect, useState } from 'react'
import { getPresets } from '../api/client'
import type { PrinterPreset } from '../api/types'

let cache: PrinterPreset[] | null = null
let pending: Promise<PrinterPreset[]> | null = null

function loadPresets(): Promise<PrinterPreset[]> {
  pending ??= getPresets().then(
    (presets) => (cache = presets),
    () => {
      pending = null // allow a later mount to retry
      return []
    },
  )
  return pending
}

/** Printer presets, fetched once per page load; `[]` until loaded or on failure. */
export function usePresets(): PrinterPreset[] {
  const [presets, setPresets] = useState<PrinterPreset[]>(() => cache ?? [])

  useEffect(() => {
    if (cache !== null) return
    let live = true
    void loadPresets().then((p) => {
      if (live) setPresets(p)
    })
    return () => {
      live = false
    }
  }, [])

  return presets
}
