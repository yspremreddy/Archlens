import { useEffect, useState } from 'react'
import { Dashboard } from './views/Dashboard'
import { UploadView } from './views/UploadView'
import { ReviewView } from './views/ReviewView'
import { SearchView } from './views/SearchView'
import { GraphView } from './views/GraphView'
import { EvaluationView } from './views/EvaluationView'
import { getTheme, setTheme, type ThemePreference } from './storage/preferences'

// Single scrollable page (Phase 9 redesign): every section renders at
// once, in document order, and the nav scrolls to a section instead of
// switching which one is mounted. No React Router — still just anchor
// links + scrollIntoView (engineering guideline 8, no new major dependency).
const SECTIONS = [
  { id: 'overview', label: 'Overview', component: Dashboard },
  { id: 'upload', label: 'Upload', component: UploadView },
  { id: 'review', label: 'Review', component: ReviewView },
  { id: 'evidence', label: 'Evidence', component: SearchView },
  { id: 'graph', label: 'Graph', component: GraphView },
  { id: 'evaluation', label: 'Evaluation', component: EvaluationView },
] as const

type SectionId = (typeof SECTIONS)[number]['id']

function App() {
  const [theme, setThemeState] = useState<ThemePreference>(() => getTheme())
  const [activeSection, setActiveSection] = useState<SectionId>('overview')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  // Highlights the current section in the nav as the user scrolls, using
  // whichever section is most visible near the top of the viewport —
  // purely a UI affordance, doesn't affect what's rendered. Each section
  // component (views/*.tsx) already renders its own <section id="...">,
  // so this observes those real DOM nodes directly rather than adding an
  // extra wrapper element per section.
  useEffect(() => {
    const elements = SECTIONS.map((s) => document.getElementById(s.id)).filter(
      (el): el is HTMLElement => el !== null,
    )
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0]
        if (visible) setActiveSection(visible.target.id as SectionId)
      },
      { rootMargin: '-45% 0px -50% 0px', threshold: [0, 0.25, 0.5, 0.75, 1] },
    )
    for (const el of elements) observer.observe(el)
    return () => observer.disconnect()
  }, [])

  function toggleTheme() {
    const next: ThemePreference = theme === 'light' ? 'dark' : 'light'
    setThemeState(next)
    setTheme(next)
  }

  function scrollToSection(id: SectionId) {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    setActiveSection(id)
  }

  return (
    <div className="app-shell">
      <a href="#main-content" className="skip-link">
        Skip to main content
      </a>
      <header className="app-header">
        <div>
          <h1>ArchLens</h1>
          <p className="app-tagline">AI Architecture Risk &amp; Compliance Reviewer</p>
        </div>
        <button className="btn btn-secondary" onClick={toggleTheme} aria-pressed={theme === 'dark'}>
          {theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        </button>
      </header>

      <nav aria-label="Page sections" className="sticky-nav">
        <ul className="tabs" role="list">
          {SECTIONS.map((section) => (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                aria-current={activeSection === section.id ? 'true' : undefined}
                onClick={(e) => {
                  e.preventDefault()
                  scrollToSection(section.id)
                }}
              >
                {section.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <main id="main-content" className="single-page">
        <p className="page-intro">
          Upload architecture evidence, ask a review question, see the verdict, inspect the
          evidence behind it, explore how components connect, and check how well ArchLens
          performs — all on this one page.
        </p>
        {SECTIONS.map((section, i) => {
          const Component = section.component
          return (
            <div key={section.id}>
              <Component />
              {i < SECTIONS.length - 1 && <hr className="section-divider" />}
            </div>
          )
        })}
      </main>
    </div>
  )
}

export default App
