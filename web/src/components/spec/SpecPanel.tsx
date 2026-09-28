import type { ReactElement, ReactNode } from 'react'
import type { JointSpec, MaleSide, PartitionSpec, PrinterPreset, PrintVolume } from '../../api/types'
import { useDataStore } from '../../store/data'
import { JointForm } from './JointForm'
import { PartitionForm } from './PartitionForm'
import { PlanSummary } from './PlanSummary'
import { PrintVolumeForm } from './PrintVolumeForm'
import { UploadForm } from './UploadForm'

export interface SpecPanelProps {
  presets: PrinterPreset[]
  uploading: boolean
  uploadError: string | null
  onUpload(file: File, scale: number): void
}

function Section({ title, children }: { title: string; children: ReactNode }): ReactElement {
  return (
    <section className="section">
      <h2 className="section-title">{title}</h2>
      {children}
    </section>
  )
}

export function SpecPanel({ presets, uploading, uploadError, onUpload }: SpecPanelProps): ReactElement {
  const spec = useDataStore((s) => s.spec)
  const patchSpec = useDataStore((s) => s.patchSpec)
  const model = useDataStore((s) => s.model)
  const plan = useDataStore((s) => s.plan)
  const planError = useDataStore((s) => s.planError)
  return (
    <>
      <Section title="Model">
        <UploadForm uploading={uploading} error={uploadError} onUpload={onUpload} />
      </Section>
      <Section title="Print volume">
        <PrintVolumeForm
          value={spec.print_volume}
          presets={presets}
          onChange={(print_volume: PrintVolume) => patchSpec({ print_volume })}
        />
      </Section>
      <Section title="Partition">
        <PartitionForm value={spec.partition} onChange={(partition: PartitionSpec) => patchSpec({ partition })} />
      </Section>
      <Section title="Joints">
        <JointForm
          value={spec.joint}
          maleSide={spec.male_side}
          resolvedJoint={plan?.resolved_joint ?? null}
          onChange={(joint: JointSpec) => patchSpec({ joint })}
          onMaleSideChange={(male_side: MaleSide) => patchSpec({ male_side })}
        />
      </Section>
      <Section title="Plan">
        <PlanSummary model={model} plan={plan} error={planError} joint={spec.joint} />
      </Section>
    </>
  )
}
