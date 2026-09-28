import { useCallback, useEffect, useRef } from 'react'
import { ApiError, cancelJob, getJob, sliceModel } from '../api/client'
import type { JobStatus } from '../api/types'
import { useDataStore } from '../store/data'
import { useViewStore } from '../store/view'

const POLL_MS = 400
const TERMINAL: ReadonlySet<JobStatus> = new Set(['done', 'failed', 'cancelled'])

const message = (err: unknown) => (err instanceof Error ? err.message : String(err))

export function useSliceJob(): { submit(): Promise<void>; cancel(): Promise<void> } {
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  const jobId = useRef<string | null>(null)
  const inFlight = useRef(false)
  /** Bumped on every submit/cancel/unmount so late responses of superseded calls are ignored. */
  const generation = useRef(0)

  const stop = useCallback(() => {
    if (timer.current !== null) clearInterval(timer.current)
    timer.current = null
    jobId.current = null
  }, [])

  const tick = useCallback(
    async (id: string) => {
      if (inFlight.current) return
      inFlight.current = true
      try {
        const job = await getJob(id)
        if (jobId.current !== id) return
        useDataStore.getState().setJob(job)
        if (TERMINAL.has(job.status)) {
          stop()
          if (job.status === 'done') useViewStore.getState().resetPieces()
        }
      } catch (err) {
        if (jobId.current !== id) return
        stop()
        if (err instanceof ApiError && err.status === 404) return
        const current = useDataStore.getState().job
        if (current?.job_id === id) useDataStore.getState().setJob({ ...current, status: 'failed', error: message(err) })
      } finally {
        inFlight.current = false
      }
    },
    [stop],
  )

  useEffect(
    () => () => {
      generation.current++
      stop()
    },
    [stop],
  )

  const submit = useCallback(async () => {
    const { model, spec, job } = useDataStore.getState()
    if (model === null) return
    const gen = ++generation.current
    const previous = jobId.current ?? (job !== null && !TERMINAL.has(job.status) ? job.job_id : null)
    stop()
    if (previous !== null) void cancelJob(previous).catch(() => undefined)
    try {
      const next = await sliceModel(model.model_id, spec)
      if (gen !== generation.current) return
      useDataStore.getState().setJob(next)
      if (TERMINAL.has(next.status)) {
        if (next.status === 'done') useViewStore.getState().resetPieces()
        return
      }
      jobId.current = next.job_id
      timer.current = setInterval(() => void tick(next.job_id), POLL_MS)
    } catch (err) {
      // A 404 means the model is gone; the model-gone callback already reset the store.
      if (gen !== generation.current || (err instanceof ApiError && err.status === 404)) return
      useDataStore.getState().setJob({
        job_id: '',
        model_id: model.model_id,
        status: 'failed',
        progress: 0,
        step: '',
        error: message(err),
      })
    }
  }, [stop, tick])

  const cancel = useCallback(async () => {
    const id = jobId.current ?? useDataStore.getState().job?.job_id
    if (!id) return
    generation.current++
    stop()
    await cancelJob(id).catch(() => undefined)
    try {
      const final = await getJob(id)
      if (useDataStore.getState().job?.job_id === id) useDataStore.getState().setJob(final)
    } catch {
      // Job already evicted; nothing more to show.
    }
  }, [stop])

  return { submit, cancel }
}
