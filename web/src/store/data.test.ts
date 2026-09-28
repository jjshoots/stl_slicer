import { beforeEach, describe, expect, it } from 'vitest'
import type { CutPlan, Job, MeshAsset, SliceResult } from '../api/types'
import { DEFAULT_JOINTS, DEFAULT_SPEC, useDataStore } from './data'

const bounds = { min: [0, 0, 0], max: [10, 10, 10] } as CutPlan['bounds']

const model: MeshAsset = {
  model_id: 'm1',
  filename: 'cube.stl',
  scale: 1,
  triangle_count: 12,
  bounds,
  volume: 1000,
  warnings: [],
}

const plan: CutPlan = {
  bounds,
  limits: { max_cell: [100, 100, 100], min_cell: 1 },
  cuts: { x: [], y: [], z: [] },
  cells: [],
  interfaces: [],
  warnings: [],
}

function result(jobId: string): SliceResult {
  return {
    job_id: jobId,
    model_id: 'm1',
    spec: DEFAULT_SPEC,
    plan,
    pieces: [],
    joints: [],
    stats: { piece_count: 0, input_volume: 0, output_volume: 0, max_overlap_volume: 0, duration_s: 0 },
    warnings: [],
  }
}

function job(jobId: string, status: Job['status'], withResult = false): Job {
  return { job_id: jobId, model_id: 'm1', status, progress: 0, step: '', result: withResult ? result(jobId) : null }
}

const store = () => useDataStore.getState()

beforeEach(() => {
  useDataStore.setState({ ...useDataStore.getInitialState() })
})

describe('data store', () => {
  it('setModel clears plan, job and result', () => {
    store().setPlan(plan, 'err')
    store().setJob(job('j1', 'done', true))
    store().setModel(model)
    const s = store()
    expect(s.model).toBe(model)
    expect(s.plan).toBeNull()
    expect(s.planError).toBeNull()
    expect(s.job).toBeNull()
    expect(s.result).toBeNull()
  })

  it('patchSpec shallow-merges', () => {
    store().patchSpec({ male_side: 'upper' })
    expect(store().spec.male_side).toBe('upper')
    expect(store().spec.print_volume).toEqual(DEFAULT_SPEC.print_volume)
    store().patchSpec({ print_volume: { x: 1, y: 2, z: 3 } })
    expect(store().spec.print_volume).toEqual({ x: 1, y: 2, z: 3 })
    expect(store().spec.male_side).toBe('upper')
  })

  it('setJob with a done job populates result', () => {
    store().setJob(job('j1', 'done', true))
    expect(store().result?.job_id).toBe('j1')
  })

  it('a new job with a different id clears result', () => {
    store().setJob(job('j1', 'done', true))
    store().setJob(job('j2', 'queued'))
    expect(store().job?.job_id).toBe('j2')
    expect(store().result).toBeNull()
  })

  it('a running job with the same id keeps result', () => {
    store().setJob(job('j1', 'done', true))
    store().setJob(job('j1', 'running'))
    expect(store().result?.job_id).toBe('j1')
  })

  it('reset clears model state but keeps the spec', () => {
    store().patchSpec({ male_side: 'upper' })
    store().setModel(model)
    store().setPlan(plan)
    store().setJob(job('j1', 'done', true))
    store().setUploadError('bad')
    store().setUploading(true)
    store().reset()
    const s = store()
    expect(s.model).toBeNull()
    expect(s.plan).toBeNull()
    expect(s.job).toBeNull()
    expect(s.result).toBeNull()
    expect(s.uploadError).toBeNull()
    expect(s.uploading).toBe(false)
    expect(s.spec.male_side).toBe('upper')
  })

  it('sized joint defaults are auto-sized', () => {
    expect(DEFAULT_JOINTS.dowel.auto).toBe(true)
    expect(DEFAULT_JOINTS.dovetail.auto).toBe(true)
    expect(DEFAULT_JOINTS.jigsaw.auto).toBe(true)
    expect(DEFAULT_JOINTS.none).toEqual({ kind: 'none' })
  })
})
