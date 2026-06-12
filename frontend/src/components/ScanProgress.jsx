import { useEffect, useRef, useState } from 'react'
import './ScanProgress.css'

const API = 'http://127.0.0.1:8000'

export default function ScanProgress({ persons, folder, onDone, onBack }) {
  const [results, setResults] = useState([])
  const [total, setTotal] = useState(0)
  const [scanned, setScanned] = useState(0)
  const [matchedBy, setMatchedBy] = useState({})
  const [status, setStatus] = useState('Connecting to scanner')
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)

  const esRef = useRef(null)
  const logRef = useRef(null)
  const allResults = useRef([])
  const matchRef = useRef({})

  useEffect(() => {
    startScan()
    return () => esRef.current?.close()
  }, [])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [results])

  function startScan() {
    setDone(false)
    setError(null)
    setResults([])
    setScanned(0)
    setMatchedBy({})
    allResults.current = []
    matchRef.current = {}

    const eventSource = new EventSource(`${API}/scan/${folder.id}`)
    esRef.current = eventSource

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'start') {
        const init = {}
        data.persons.forEach((name) => { init[name] = 0 })
        setTotal(data.total)
        setMatchedBy(init)
        matchRef.current = init
        setStatus(`Scanning ${data.total} photos in ${data.folder_name}`)
      }

      if (data.type === 'progress') {
        setScanned(data.index)

        if (data.persons_matched?.length) {
          const updated = { ...matchRef.current }
          data.persons_matched.forEach((personMatch) => {
            updated[personMatch.name] = (updated[personMatch.name] || 0) + 1
          })
          matchRef.current = updated
          setMatchedBy({ ...updated })
        }

        allResults.current.push(data)
        setResults((prev) => [...prev, data])
      }

      if (data.type === 'done') {
        eventSource.close()
        setDone(true)
        setStatus(`Finished scanning ${data.total} photos`)
        onDone(allResults.current, data)
      }

      if (data.type === 'error') {
        eventSource.close()
        setError(data.message)
        setStatus('Scan failed')
      }
    }

    eventSource.onerror = () => {
      if (!done) {
        setError('Connection lost. Make sure the backend is running.')
        eventSource.close()
      }
    }
  }

  function stopAndSeeResults() {
    esRef.current?.close()
    setDone(true)
    setStatus('Scan stopped')
    onDone(allResults.current, {
      total: scanned,
      matched_by_person: matchRef.current,
      skipped: 0,
    })
  }

  const pct = total > 0 ? Math.round((scanned / total) * 100) : 0
  const totalMatched = Object.values(matchedBy).reduce((sum, count) => sum + count, 0)
  const cachedCount = results.filter((result) => result.cached).length
  const retriedCount = results.filter((result) => result.retried).length

  return (
    <section className="scan-wrap">
      <div className="workflow-card scan-card">
        <div className="scan-header">
          <div>
            <p className="eyebrow">Step 3</p>
            <h1>{done ? 'Scan complete' : 'Scanning photos'}</h1>
            <p>{status}</p>
          </div>
          <div className="scan-thumbs">
            {persons.map((person) => (
              <img key={person.name} src={person.previewUrl} alt={person.name} className="selfie-thumb" />
            ))}
          </div>
        </div>

        <div className="progress-block">
          <div className="progress-meta">
            <span>{scanned} of {total || 0}</span>
            <strong>{pct}%</strong>
          </div>
          <div className="progress-track">
            <div className={`progress-fill ${done ? 'complete' : ''}`} style={{ width: `${pct}%` }} />
          </div>
        </div>

        <div className="stat-row">
          <Metric label="Total" value={total} />
          <Metric label="Scanned" value={scanned} />
          <Metric label="Matches" value={totalMatched} intent="success" />
          <Metric label="Cached" value={cachedCount} />
          <Metric label="Retried" value={retriedCount} />
        </div>

        <div className="person-counts">
          {persons.map((person) => (
            <div key={person.name} className="person-count">
              <img src={person.previewUrl} alt={person.name} />
              <span>{person.name}</span>
              <strong>{matchedBy[person.name] || 0}</strong>
            </div>
          ))}
        </div>

        <div className="log-box" ref={logRef}>
          {results.length === 0 && (
            <div className="log-waiting"><span className="pulse-dot" /> Waiting for first photo</div>
          )}

          {results.map((result, index) => (
            <div key={`${result.file_id}-${index}`} className={`log-row ${result.any_match ? 'log-match' : ''}`}>
              <span className="log-state">{result.skipped ? 'ERR' : result.any_match ? 'MATCH' : 'SCAN'}</span>
              <span className="log-name" title={result.name}>{result.name}</span>
              {result.persons_matched?.map((personMatch) => (
                <span key={personMatch.name} className={`confidence-chip ${personMatch.confidence_label}`}>
                  {personMatch.name} {(personMatch.confidence * 100).toFixed(0)}%
                </span>
              ))}
              {result.cached && <span className="mini-chip">cached</span>}
              {result.retried && <span className="mini-chip accent">retry</span>}
            </div>
          ))}
        </div>

        {error && <div className="error-box">{error}</div>}

        <div className="scan-actions">
          {!done ? (
            <>
              <button className="btn-secondary" onClick={onBack}>Back</button>
              <button className="btn-stop" onClick={stopAndSeeResults}>
                Stop and view results
                {totalMatched > 0 && <span>{totalMatched}</span>}
              </button>
            </>
          ) : (
            <>
              <button className="btn-secondary" onClick={onBack}>Change folder</button>
              <button className="btn-primary" onClick={() => onDone(allResults.current, { matched_by_person: matchedBy })}>
                View results
              </button>
            </>
          )}
        </div>
      </div>
    </section>
  )
}

function Metric({ label, value, intent }) {
  return (
    <div className={`stat-card ${intent || ''}`}>
      <span className="stat-val">{value}</span>
      <span className="stat-lbl">{label}</span>
    </div>
  )
}
