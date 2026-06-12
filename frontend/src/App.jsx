import { useState } from 'react'
import SelfieUpload from './components/SelfieUpload.jsx'
import FolderPicker from './components/FolderPicker.jsx'
import ScanProgress from './components/ScanProgress.jsx'
import ResultsGrid from './components/ResultsGrid.jsx'
import './App.css'

export default function App() {
  const [step, setStep] = useState(1)
  const [theme, setTheme] = useState('light')
  const [persons, setPersons] = useState([])
  const [folder, setFolder] = useState(null)
  const [results, setResults] = useState([])
  const [stats, setStats] = useState(null)

  const steps = ['Selfie', 'Folder', 'Scan', 'Results']

  function handleSelfieUploaded(personsData) {
    setPersons(personsData)
    setStep(2)
  }

  function handleFolderSelected(selectedFolder) {
    setFolder(selectedFolder)
    setStep(3)
  }

  function handleScanDone(allResults, scanStats) {
    setResults(allResults)
    setStats(scanStats)
    setStep(4)
  }

  function reset() {
    setStep(1)
    setPersons([])
    setFolder(null)
    setResults([])
    setStats(null)
  }

  return (
    <div className={`app-shell theme-${theme}`}>
      <header className="app-header">
        <div className="brand-lockup">
          <div className="brand-mark">TF</div>
          <div>
            <div className="logo-text">TripFace</div>
            <div className="logo-sub">Private photo matching</div>
          </div>
        </div>

        <nav className="stepper" aria-label="Scan progress">
          {steps.map((label, index) => {
            const stepNumber = index + 1
            return (
              <div
                key={label}
                className={`step-dot ${step === stepNumber ? 'active' : ''} ${step > stepNumber ? 'done' : ''}`}
              >
                <div className="dot-circle">{step > stepNumber ? 'OK' : stepNumber}</div>
                <span className="dot-label">{label}</span>
              </div>
            )
          })}
        </nav>

        <button
          className="theme-toggle"
          onClick={() => setTheme((current) => current === 'light' ? 'dark' : 'light')}
          aria-label="Toggle dark mode"
        >
          <span className="theme-toggle-track">
            <span className="theme-toggle-thumb" />
          </span>
          <span>{theme === 'light' ? 'Dark' : 'Light'}</span>
        </button>
      </header>

      <main className="app-main">
        {step === 1 && <SelfieUpload onUploaded={handleSelfieUploaded} />}
        {step === 2 && (
          <FolderPicker
            persons={persons}
            onSelected={handleFolderSelected}
            onBack={() => setStep(1)}
          />
        )}
        {step === 3 && (
          <ScanProgress
            persons={persons}
            folder={folder}
            onDone={handleScanDone}
            onBack={() => setStep(2)}
          />
        )}
        {step === 4 && (
          <ResultsGrid
            results={results}
            stats={stats}
            persons={persons}
            folder={folder}
            onReset={reset}
          />
        )}
      </main>
    </div>
  )
}
