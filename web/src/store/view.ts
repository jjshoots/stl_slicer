import { create } from 'zustand'

export interface ViewState {
  explode: number
  showPlanes: boolean
  hidden: Set<string>
  selected: string | null

  setExplode(explode: number): void
  setShowPlanes(show: boolean): void
  toggleHidden(id: string): void
  select(id: string | null): void
  /** Called when pieces change (new job result): clears hidden + selected. */
  resetPieces(): void
}

export const useViewStore = create<ViewState>((set) => ({
  explode: 0,
  showPlanes: true,
  hidden: new Set<string>(),
  selected: null,

  setExplode: (explode) => set({ explode: Math.min(1, Math.max(0, explode)) }),
  setShowPlanes: (showPlanes) => set({ showPlanes }),
  toggleHidden: (id) =>
    set((s) => {
      const hidden = new Set(s.hidden)
      if (hidden.has(id)) hidden.delete(id)
      else hidden.add(id)
      return { hidden }
    }),
  select: (selected) => set({ selected }),
  resetPieces: () => set({ hidden: new Set<string>(), selected: null }),
}))
