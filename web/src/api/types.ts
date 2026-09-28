/**
 * API types. Every name here is an alias onto the generated OpenAPI schema
 * (`schema.d.ts`, produced by `npm run gen` from the backend's `openapi.json`).
 * This is the only module the rest of the app imports API types from.
 */
import type { components } from './schema'

type S = components['schemas']

export type Vec3 = [number, number, number]
export type Axis = S['Axis']
export type Bounds = S['Bounds']
export type PrintVolume = S['PrintVolume']
export type CellLimits = S['CellLimits']
export type AxisCuts = S['AxisCuts']
export type CellIndex = S['CellIndex']
export type Cell = S['Cell']
export type PlaneFrame = S['PlaneFrame']
export type CutInterface = S['CutInterface']
export type WarningCode = S['WarningCode']
export type SliceWarning = S['SliceWarning']
export type CutPlan = S['CutPlan']
export type NoJointSpec = S['NoJointSpec']
export type DowelJointSpec = S['DowelJointSpec']
export type DovetailJointSpec = S['DovetailJointSpec']
export type JointSpec = NoJointSpec | DowelJointSpec | DovetailJointSpec
export type JointKind = JointSpec['kind']
export type MaleSide = S['MaleSide']
export type PartitionSpec = S['PartitionSpec']
export type SliceSpec = S['SliceSpec']
export type Placement = S['Placement']
export type JointInfo = S['JointInfo']
export type MeshAsset = S['MeshAsset']
export type PieceInfo = S['PieceInfo']
export type SliceStats = S['SliceStats']
export type SliceResult = S['SliceResult']
export type JobStatus = S['JobStatus']
export type Job = S['Job']
export type PrinterPreset = S['PrinterPreset']
