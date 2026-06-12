import { useMemo, useState } from 'react'
import axios from 'axios'
import './ResultsGrid.css'

const API = 'http://127.0.0.1:8000'

export default function ResultsGrid({ results, stats, persons, folder, onReset }) {
  const [filter, setFilter] = useState('all_match')
  const [saveModal, setSaveModal] = useState(null)
  const [folderName, setFolderName] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveResult, setSaveResult] = useState(null)
  const [saveError, setSaveError] = useState(null)

  const matchedByPerson = stats?.matched_by_person || {}
  const allMatchCount = results.filter((result) => result.any_match).length
  const bothCount = results.filter((result) => result.both_match).length
  const skippedCount = results.filter((result) => result.skipped).length

  const filtered = useMemo(() => results.filter((result) => {
    if (filter === 'all_match') return result.any_match
    if (filter === 'both') return result.both_match
    if (filter === 'skipped') return result.skipped
    return result.persons_matched?.some((personMatch) => personMatch.name === filter)
  }), [results, filter])

  function openSaveModal(personName) {
    const fileIds = results
      .filter((result) => result.persons_matched?.some((personMatch) => personMatch.name === personName))
      .map((result) => result.file_id)

    setSaveModal({ personName, fileIds })
    setFolderName(`${personName} - Trip Photos`)
    setSaveResult(null)
    setSaveError(null)
  }

  function openSaveAll() {
    const fileIds = [...new Set(results.filter((result) => result.any_match).map((result) => result.file_id))]
    setSaveModal({ personName: 'All Matches', fileIds })
    setFolderName('Trip Photos - All Matches')
    setSaveResult(null)
    setSaveError(null)
  }

  async function handleSave() {
    if (!folderName.trim() || !saveModal) return
    setSaving(true)
    setSaveError(null)
    try {
      const response = await axios.post(`${API}/drive/save`, {
        file_ids: saveModal.fileIds,
        folder_name: folderName.trim(),
      })
      setSaveResult(response.data)
    } catch (err) {
      setSaveError(err.response?.data?.detail || 'Save failed.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="results-wrap">
      {saveModal && (
        <div className="modal-overlay" onClick={() => !saving && setSaveModal(null)}>
          <div className="modal-box" onClick={(event) => event.stopPropagation()}>
            {!saveResult ? (
              <>
                <div>
                  <p className="eyebrow">Google Drive</p>
                  <h2 className="modal-title">Save matched photos</h2>
                  <p className="modal-sub">{saveModal.fileIds.length} photos for <strong>{saveModal.personName}</strong></p>
                </div>
                <label className="modal-label">
                  Folder name
                  <input
                    className="modal-input"
                    value={folderName}
                    onChange={(event) => setFolderName(event.target.value)}
                    placeholder="Rahul - Goa Trip"
                    autoFocus
                    onKeyDown={(event) => event.key === 'Enter' && handleSave()}
                  />
                </label>
                {saveError && <div className="error-box">{saveError}</div>}
                <div className="modal-actions">
                  <button className="btn-secondary" onClick={() => setSaveModal(null)} disabled={saving}>Cancel</button>
                  <button className="btn-primary" onClick={handleSave} disabled={saving || !folderName.trim()}>
                    {saving ? <><span className="spinner" /> Saving</> : 'Save to Drive'}
                  </button>
                </div>
              </>
            ) : (
              <div className="save-success">
                <div className="success-icon">OK</div>
                <h2 className="modal-title">{saveResult.created ? 'Folder created' : 'Saved to folder'}</h2>
                <p className="modal-sub">
                  <strong>{saveResult.copied}</strong> photos saved to <strong>{saveResult.folder_name}</strong>
                  {saveResult.failed > 0 && `, ${saveResult.failed} failed`}
                </p>
                <a
                  className="btn-drive"
                  href={`https://drive.google.com/drive/folders/${saveResult.folder_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Open Drive folder
                </a>
                <button className="btn-secondary" onClick={() => setSaveModal(null)}>Close</button>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="results-banner">
        <div>
          <p className="eyebrow">Step 4</p>
          <h1>Matched photos</h1>
          <p>{folder?.name ? `Folder: ${folder.name}` : 'Scan results'}</p>
        </div>
        <div className="banner-actions">
          <button className="btn-secondary" onClick={onReset}>New scan</button>
          <button className="btn-primary" onClick={openSaveAll} disabled={allMatchCount === 0}>Save all</button>
        </div>
      </div>

      <div className="summary-grid">
        <Summary label="Scanned" value={results.length} />
        <Summary label="Matches" value={allMatchCount} intent="success" />
        <Summary label="Both" value={bothCount} />
        <Summary label="Skipped" value={skippedCount} />
      </div>

      <div className="person-summary">
        {persons.map((person) => (
          <article key={person.name} className="person-result">
            <img src={person.previewUrl} alt={person.name} />
            <div>
              <strong>{person.name}</strong>
              <span>{matchedByPerson[person.name] || 0} matched photos</span>
            </div>
            <button className="btn-secondary compact" onClick={() => openSaveModal(person.name)} disabled={!matchedByPerson[person.name]}>
              Save
            </button>
          </article>
        ))}
      </div>

      <div className="filter-tabs">
        <FilterButton active={filter === 'all_match'} onClick={() => setFilter('all_match')} label="All matches" count={allMatchCount} />
        {persons.map((person) => (
          <FilterButton
            key={person.name}
            active={filter === person.name}
            onClick={() => setFilter(person.name)}
            label={person.name}
            count={matchedByPerson[person.name] || 0}
          />
        ))}
        {persons.length > 1 && (
          <FilterButton active={filter === 'both'} onClick={() => setFilter('both')} label="Both" count={bothCount} />
        )}
        <FilterButton active={filter === 'skipped'} onClick={() => setFilter('skipped')} label="Skipped" count={skippedCount} />
      </div>

      {filtered.length === 0 ? (
        <div className="empty-state">
          <strong>No photos in this view</strong>
          <span>Try another filter or run a new scan.</span>
        </div>
      ) : (
        <div className="photo-grid">
          {filtered.map((result, index) => (
            <PhotoCard key={result.file_id || index} result={result} index={index} />
          ))}
        </div>
      )}
    </section>
  )
}

function Summary({ label, value, intent }) {
  return (
    <div className={`summary-card ${intent || ''}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  )
}

function FilterButton({ active, onClick, label, count }) {
  return (
    <button className={`ftab ${active ? 'active' : ''}`} onClick={onClick}>
      {label}
      <span>{count}</span>
    </button>
  )
}

function PhotoCard({ result, index }) {
  const driveUrl = `https://drive.google.com/file/d/${result.file_id}/view`

  return (
    <a
      href={driveUrl}
      target="_blank"
      rel="noopener noreferrer"
      className={`photo-card ${result.both_match ? 'card-both' : result.any_match ? 'card-match' : ''}`}
      style={{ animationDelay: `${Math.min(index * 0.025, 0.35)}s` }}
    >
      <div className="card-thumb">
        <span>{result.both_match ? 'BOTH' : result.any_match ? 'MATCH' : result.skipped ? 'ERROR' : 'SCAN'}</span>
      </div>

      <div className="card-info">
        <strong className="card-name" title={result.name}>{result.name}</strong>
        <div className="card-persons">
          {result.persons_matched?.map((personMatch) => (
            <span key={personMatch.name} className={`card-person-tag ${personMatch.confidence_label}`}>
              {personMatch.name} {(personMatch.confidence * 100).toFixed(0)}%
            </span>
          ))}
        </div>
        <div className="card-meta">
          <span>{result.faces_detected || 0} faces</span>
          <span>Open</span>
        </div>
      </div>
    </a>
  )
}
