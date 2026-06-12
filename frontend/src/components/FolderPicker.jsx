import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import './FolderPicker.css'

const API = 'http://127.0.0.1:8000'

export default function FolderPicker({ persons, onSelected, onBack }) {
  const [folders, setFolders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    axios.get(`${API}/drive/folders`)
      .then((response) => {
        setFolders(response.data.folders)
        setLoading(false)
      })
      .catch(() => {
        setError('Could not load Google Drive folders.')
        setLoading(false)
      })
  }, [])

  const filtered = useMemo(() => (
    folders.filter((folder) => folder.name.toLowerCase().includes(search.toLowerCase()))
  ), [folders, search])

  return (
    <section className="picker-wrap">
      <div className="workflow-card">
        <div className="picker-header">
          <div>
            <p className="eyebrow">Step 2</p>
            <h1>Choose a Drive folder</h1>
            <p>Scanning for <strong>{persons.map((person) => person.name).join(' and ')}</strong></p>
          </div>
          <div className="persons-thumbs">
            {persons.map((person) => (
              <div key={person.name} className="thumb-wrap" title={person.name}>
                <img src={person.previewUrl} alt={person.name} className="selfie-thumb" />
              </div>
            ))}
          </div>
        </div>

        <label className="search-wrap">
          <span>Search</span>
          <input
            className="search-input"
            placeholder="Filter folders by name"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>

        <div className="folder-list">
          {loading && [...Array(6)].map((_, index) => (
            <div key={index} className="folder-skeleton" style={{ animationDelay: `${index * 0.06}s` }} />
          ))}

          {error && <div className="list-error">{error}</div>}

          {!loading && !error && filtered.length === 0 && (
            <div className="list-empty">No folders match "{search}".</div>
          )}

          {!loading && filtered.map((folder) => (
            <button
              key={folder.id}
              className={`folder-row ${selected?.id === folder.id ? 'selected' : ''}`}
              onClick={() => setSelected(folder)}
            >
              <span className="folder-token">DIR</span>
              <span className="folder-info">
                <span className="folder-name">{folder.name}</span>
                <span className="folder-date">
                  {folder.modifiedTime ? new Date(folder.modifiedTime).toLocaleDateString() : 'No modified date'}
                </span>
              </span>
              {selected?.id === folder.id && <span className="folder-check">Selected</span>}
            </button>
          ))}
        </div>

        <div className="picker-actions">
          <button className="btn-secondary" onClick={onBack}>Back</button>
          <button className="btn-primary" disabled={!selected} onClick={() => onSelected(selected)}>
            Start scan
          </button>
        </div>
      </div>
    </section>
  )
}
