import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { SliceSpec } from './types'
import {
  ApiError,
  cancelJob,
  deleteModel,
  downloadZipUrl,
  getJob,
  getModel,
  modelMeshUrl,
  pieceStlUrl,
  piecesGlbUrl,
  planModel,
  setOnModelGone,
  sliceModel,
  uploadModel,
} from './client'

const spec: SliceSpec = {
  print_volume: { x: 200, y: 200, z: 200 },
  partition: { cuts: null, bed_margin: 2 },
  joint: { kind: 'none' },
  male_side: 'lower',
}

const fetchMock = vi.fn<typeof fetch>()

function reply(status: number, body: unknown, statusText = ''): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    statusText,
    headers: { 'Content-Type': 'application/json' },
  })
}

function lastCall(): [string, RequestInit] {
  const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1]
  return [String(url), init ?? {}]
}

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  setOnModelGone(null)
})

describe('client', () => {
  it('uploads a model as multipart form data', async () => {
    fetchMock.mockResolvedValue(reply(200, { model_id: 'm1' }))
    const file = new File(['solid'], 'cube.stl')
    const asset = await uploadModel(file, 2.5)
    expect(asset.model_id).toBe('m1')
    const [url, init] = lastCall()
    expect(url).toBe('/api/models')
    expect(init.method).toBe('POST')
    const form = init.body
    expect(form).toBeInstanceOf(FormData)
    expect((form as FormData).get('file')).toBeInstanceOf(File)
    expect((form as FormData).get('scale')).toBe('2.5')
  })

  it('posts plan and slice specs as JSON', async () => {
    fetchMock.mockImplementation(async () => reply(200, {}))
    const ctrl = new AbortController()
    await planModel('m1', spec, ctrl.signal)
    let [url, init] = lastCall()
    expect(url).toBe('/api/models/m1/plan')
    expect(init.method).toBe('POST')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(init.body).toBe(JSON.stringify(spec))
    expect(init.signal).toBe(ctrl.signal)

    await sliceModel('m1', spec)
    ;[url, init] = lastCall()
    expect(url).toBe('/api/models/m1/slice')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
    expect(init.body).toBe(JSON.stringify(spec))
  })

  it('gets and cancels jobs', async () => {
    fetchMock.mockResolvedValueOnce(reply(200, { job_id: 'j1', status: 'running' }))
    const job = await getJob('j1')
    expect(job.status).toBe('running')
    expect(lastCall()[0]).toBe('/api/jobs/j1')

    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await cancelJob('j1')
    const [url, init] = lastCall()
    expect(url).toBe('/api/jobs/j1')
    expect(init.method).toBe('DELETE')
  })

  it('treats 404 on cancelJob/deleteModel as success without the model-gone callback', async () => {
    const gone = vi.fn()
    setOnModelGone(gone)
    fetchMock.mockImplementation(async () => reply(404, { detail: 'nope' }))
    await expect(cancelJob('j1')).resolves.toBeUndefined()
    await expect(deleteModel('m1')).resolves.toBeUndefined()
    expect(gone).not.toHaveBeenCalled()
  })

  it('notifies the model-gone callback on a model-scoped 404', async () => {
    const gone = vi.fn()
    setOnModelGone(gone)
    fetchMock.mockResolvedValue(reply(404, { detail: 'model not found' }))
    const err = await getModel('m9').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(404)
    expect((err as ApiError).detail).toBe('model not found')
    expect(gone).toHaveBeenCalledWith('m9')
  })

  it('does not notify the model-gone callback for a job 404', async () => {
    const gone = vi.fn()
    setOnModelGone(gone)
    fetchMock.mockResolvedValue(reply(404, { detail: 'job not found' }))
    await expect(getJob('j1')).rejects.toBeInstanceOf(ApiError)
    expect(gone).not.toHaveBeenCalled()
  })

  it('joins FastAPI validation messages', async () => {
    fetchMock.mockResolvedValue(reply(422, { detail: [{ loc: ['body'], msg: 'x', type: 'value_error' }] }))
    const err = await planModel('m1', spec).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).status).toBe(422)
    expect((err as ApiError).detail).toBe('x')
  })

  it('falls back to statusText for non-JSON errors', async () => {
    fetchMock.mockResolvedValue(new Response('boom', { status: 500, statusText: 'Server Error' }))
    await expect(getJob('j1')).rejects.toMatchObject({ status: 500, detail: 'Server Error' })
  })

  it('rethrows AbortError unchanged', async () => {
    const abort = new DOMException('aborted', 'AbortError')
    fetchMock.mockRejectedValue(abort)
    await expect(planModel('m1', spec)).rejects.toBe(abort)
  })

  it('builds asset URLs', () => {
    expect(modelMeshUrl('m1')).toBe('/api/models/m1/mesh.glb')
    expect(piecesGlbUrl('j1')).toBe('/api/jobs/j1/pieces.glb')
    expect(pieceStlUrl('j1', 'x0_y0_z0_c0')).toBe('/api/jobs/j1/pieces/x0_y0_z0_c0.stl')
    expect(downloadZipUrl('j1')).toBe('/api/jobs/j1/download.zip')
  })
})
