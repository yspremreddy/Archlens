import { useEffect, useState } from 'react'
import { Dashboard } from './views/Dashboard'
import { UploadView } from './views/UploadView'
import { ReviewView } from './views/ReviewView'
import { SearchView } from './views/SearchView'
import { GraphView } from './views/GraphView'
import { EvaluationView } from './views/EvaluationView'
import { getTheme, setTheme, type ThemePreference } from './storage/preferences'

// Tab/state-based view switching instead of React Router — avoids
// adding a new major dependency for what is a small, single-page app
// (CLAUDE.md rule 8).
const TABS = [
  { id: 'dashboard', label: 'Dashboard', component: Dashboard },
  { id: 'upload', label: 'Upload', component: UploadView },
  { id: 'review', label: 'Review', component: ReviewView },
  { id: 'search', label: 'Search', component: SearchView },
  { id: 'graph', label: 'Graph', component: GraphView },
  { id: 'evaluation', label: 'Evaluation', component: EvaluationView },
] as const

type TabId = (typeof TABS)[number]['id']

function App() {
  const [activeTab, setActiveTab] = useState<TabId>('dashboard')
  const [theme, setThemeState] = useState<ThemePreference>(() => getTheme())

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  function toggleTheme() {
    const next: ThemePreference = theme === 'light' ? 'dark' : 'light'
    setThemeState(next)
    setTheme(next)
  }

  const ActiveComponent = TABS.find((t) => t.id === activeTab)?.component ?? Dashboard

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <header className="app-header">
        <h1>ArchLens</h1>
        <button className="btn btn-secondary" onClick={toggleTheme} aria-pressed={theme === 'dark'}>
          {theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        </button>
      </header>

      <nav aria-label="Main sections">
        <ul className="tabs" role="tablist">
          {TABS.map((tab) => (
            <li key={tab.id} role="presentation">
              <button
                role="tab"
                id={`tab-${tab.id}`}
                aria-selected={activeTab === tab.id}
                aria-controls={`panel-${tab.id}`}
                tabIndex={activeTab === tab.id ? 0 : -1}
                onClick={() => setActiveTab(tab.id)}
              >
                {tab.label}
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <main
        id="main-content"
        role="tabpanel"
        aria-labelledby={`tab-${activeTab}`}
        className="panel"
      >
        <ActiveComponent />
      </main>
    </div>
  )
}

export default App
