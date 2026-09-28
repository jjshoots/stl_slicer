import type { ReactElement, ReactNode } from 'react'

export interface AppShellProps {
  sidebar: ReactNode
  viewer: ReactNode
  footer?: ReactNode
}

export function AppShell({ sidebar, viewer, footer }: AppShellProps): ReactElement {
  return (
    <div className="app">
      <aside className="sidebar">
        <header className="sidebar-header">
          <h1>stl-slicer</h1>
          <span className="muted">partition · joint · print</span>
        </header>
        <div className="sidebar-body">{sidebar}</div>
      </aside>
      <main className="viewer-pane">
        {viewer}
        {footer && <div className="viewer-overlay">{footer}</div>}
      </main>
    </div>
  )
}
