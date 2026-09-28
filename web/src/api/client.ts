import type { CutPlan, Job, MeshAsset, PrinterPreset, SliceSpec } from './types'

export class ApiError extends Error {
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

let onModelGone: ((modelId: string) => void) | null = null

/** Registered callback invoked when any request under /api/models/{id} (or a slice/plan of it) returns 404; receives the model id. */
export function setOnModelGone(cb: ((modelId: string) => void) | null): void {
  onModelGone = cb
}

async function errorDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json()
    if (typeof body === 'object' && body !== null && 'detail' in body) {
      const { detail } = body
      if (typeof detail === 'string') return detail
      if (Array.isArray(detail)) {
        const msgs = detail
          .map((d: unknown) => (typeof d === 'object' && d !== null && 'msg' in d && typeof d.msg === 'string' ? d.msg : null))
          .filter((m): m is string => m !== null)
        if (msgs.length > 0) return msgs.join('; ')
      }
    }
  } catch {
    // Not JSON: fall through to statusText.
  }
  return res.statusText || `HTTP ${res.status}`
}

/** Fetch `path`; non-2xx throws ApiError. `modelId` marks a model-scoped path whose 404 notifies the model-gone callback. */
async function send(path: string, init: RequestInit = {}, modelId?: string): Promise<Response> {
  const res = await fetch(path, init)
  if (res.ok) return res
  const detail = await errorDetail(res)
  if (res.status === 404 && modelId !== undefined) onModelGone?.(modelId)
  throw new ApiError(res.status, detail)
}

async function json<T>(path: string, init: RequestInit = {}, modelId?: string): Promise<T> {
  const res = await send(path, init, modelId)
  return (await res.json()) as T
}

/** DELETE that treats 404 as already gone. */
async function remove(path: string): Promise<void> {
  try {
    await send(path, { method: 'DELETE' })
  } catch (err) {
    if (!(err instanceof ApiError && err.status === 404)) throw err
  }
}

function postJson(body: unknown, signal?: AbortSignal): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal }
}

const modelPath = (modelId: string) => `/api/models/${encodeURIComponent(modelId)}`
const jobPath = (jobId: string) => `/api/jobs/${encodeURIComponent(jobId)}`

export function uploadModel(file: File, scale: number): Promise<MeshAsset> {
  const form = new FormData()
  form.append('file', file)
  form.append('scale', String(scale))
  return json<MeshAsset>('/api/models', { method: 'POST', body: form })
}

export function getModel(modelId: string): Promise<MeshAsset> {
  return json<MeshAsset>(modelPath(modelId), {}, modelId)
}

export function deleteModel(modelId: string): Promise<void> {
  return remove(modelPath(modelId))
}

export function planModel(modelId: string, spec: SliceSpec, signal?: AbortSignal): Promise<CutPlan> {
  return json<CutPlan>(`${modelPath(modelId)}/plan`, postJson(spec, signal), modelId)
}

export function sliceModel(modelId: string, spec: SliceSpec): Promise<Job> {
  return json<Job>(`${modelPath(modelId)}/slice`, postJson(spec), modelId)
}

export function getJob(jobId: string): Promise<Job> {
  return json<Job>(jobPath(jobId))
}

export function cancelJob(jobId: string): Promise<void> {
  return remove(jobPath(jobId))
}

export function getPresets(): Promise<PrinterPreset[]> {
  return json<PrinterPreset[]>('/api/presets')
}

export function modelMeshUrl(modelId: string): string {
  return `${modelPath(modelId)}/mesh.glb`
}

export function piecesGlbUrl(jobId: string): string {
  return `${jobPath(jobId)}/pieces.glb`
}

export function pieceStlUrl(jobId: string, pieceId: string): string {
  return `${jobPath(jobId)}/pieces/${encodeURIComponent(pieceId)}.stl`
}

export function downloadZipUrl(jobId: string): string {
  return `${jobPath(jobId)}/download.zip`
}
