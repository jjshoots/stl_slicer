import { create } from 'zustand'
import type { CutPlan, Job, JointSpec, MeshAsset, PrintVolume, SliceResult, SliceSpec } from '../api/types'

const DEFAULT_PRINT_VOLUME: PrintVolume = { x: 220, y: 220, z: 250 }

export const DEFAULT_JOINTS: { [K in JointSpec['kind']]: Extract<JointSpec, { kind: K }> } = {
  none: { kind: 'none' },
  dowel: { kind: 'dowel', diameter: 8, depth: 6, clearance: 0.15, edge_margin: 3, spacing: 40 },
  dovetail: {
    kind: 'dovetail',
    neck_width: 8,
    head_width: 12,
    depth: 6,
    clearance: 0.15,
    edge_margin: 3,
    spacing: 60,
  },
}

export const DEFAULT_SPEC: SliceSpec = {
  print_volume: DEFAULT_PRINT_VOLUME,
  partition: { cuts: null, bed_margin: 2 },
  joint: DEFAULT_JOINTS.none,
  male_side: 'lower',
}

export interface DataState {
  model: MeshAsset | null
  spec: SliceSpec
  plan: CutPlan | null
  planError: string | null
  job: Job | null
  result: SliceResult | null
  uploadError: string | null
  uploading: boolean

  setModel(model: MeshAsset | null): void
  /** Shallow-merge a partial spec; nested objects are replaced, not merged. */
  patchSpec(patch: Partial<SliceSpec>): void
  setPlan(plan: CutPlan | null, error?: string | null): void
  setJob(job: Job | null): void
  setUploadError(error: string | null): void
  setUploading(uploading: boolean): void
  /** Forget everything tied to a model (404 / delete / new upload). Keeps the spec. */
  reset(): void
}

export const useDataStore = create<DataState>((set) => ({
  model: null,
  spec: DEFAULT_SPEC,
  plan: null,
  planError: null,
  job: null,
  result: null,
  uploadError: null,
  uploading: false,

  setModel: (model) => set({ model, plan: null, planError: null, job: null, result: null }),
  patchSpec: (patch) => set((s) => ({ spec: { ...s.spec, ...patch } })),
  setPlan: (plan, error = null) => set({ plan, planError: error }),
  setJob: (job) =>
    set((s) => {
      if (job === null) return { job }
      if (job.status === 'done' && job.result) return { job, result: job.result }
      // A newer job supersedes the previous result; a still-pending same job keeps it.
      const keep = s.result !== null && s.result.job_id === job.job_id
      return { job, result: keep ? s.result : null }
    }),
  setUploadError: (uploadError) => set({ uploadError }),
  setUploading: (uploading) => set({ uploading }),
  reset: () => set({ model: null, plan: null, planError: null, job: null, result: null, uploadError: null, uploading: false }),
}))
