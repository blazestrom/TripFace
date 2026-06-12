import { useEffect, useRef, useState } from 'react'
import axios from 'axios'
import './SelfieUpload.css'

const API = 'http://127.0.0.1:8000'
const MAX_PERSONS = 2

const emptyPerson = () => ({
  name: '',
  previewUrl: null,
  blob: null,
  uploaded: false,
})

export default function SelfieUpload({ onUploaded }) {
  const [persons, setPersons] = useState([emptyPerson()])
  const [activePerson, setActivePerson] = useState(0)
  const [mode, setMode] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [streaming, setStreaming] = useState(false)

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    if (mode === 'webcam' && streamRef.current && videoRef.current) {
      videoRef.current.srcObject = streamRef.current
      videoRef.current.play().catch(() => {})
      setStreaming(true)
    }
  }, [mode])

  async function startWebcam(personIndex) {
    setError(null)
    setActivePerson(personIndex)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
      })
      streamRef.current = stream
      setMode('webcam')
    } catch {
      setError('Camera access was blocked. Allow camera permission or choose a file.')
    }
  }

  function stopWebcam() {
    streamRef.current?.getTracks().forEach((track) => track.stop())
    streamRef.current = null
    setStreaming(false)
  }

  function captureWebcam() {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return

    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)
    canvas.toBlob((blob) => {
      updatePerson(activePerson, {
        blob,
        previewUrl: URL.createObjectURL(blob),
        uploaded: false,
      })
      stopWebcam()
      setMode(null)
    }, 'image/jpeg', 0.92)
  }

  function openGallery(personIndex) {
    setActivePerson(personIndex)
    setError(null)
    setTimeout(() => {
      fileInputRef.current.removeAttribute('capture')
      fileInputRef.current.click()
    }, 50)
  }

  function openMobileCamera(personIndex) {
    setActivePerson(personIndex)
    setError(null)
    setTimeout(() => {
      fileInputRef.current.setAttribute('capture', 'user')
      fileInputRef.current.click()
    }, 50)
  }

  function handleFileChange(event) {
    const file = event.target.files[0]
    if (!file) return
    updatePerson(activePerson, {
      blob: file,
      previewUrl: URL.createObjectURL(file),
      uploaded: false,
    })
    setMode(null)
    setError(null)
    event.target.value = ''
  }

  function updatePerson(index, changes) {
    setPersons((prev) => prev.map((person, i) => (i === index ? { ...person, ...changes } : person)))
  }

  function addPerson() {
    if (persons.length >= MAX_PERSONS) return
    setPersons((prev) => [...prev, emptyPerson()])
  }

  function removePerson(index) {
    setPersons((prev) => prev.filter((_, i) => i !== index))
  }

  function clearPhoto(index) {
    updatePerson(index, { blob: null, previewUrl: null, uploaded: false })
  }

  async function handleUploadAll() {
    setError(null)

    for (let i = 0; i < persons.length; i += 1) {
      if (!persons[i].name.trim()) {
        setError(`Enter a name for Person ${i + 1}.`)
        return
      }
      if (!persons[i].blob) {
        setError(`Add a clear face photo for ${persons[i].name || `Person ${i + 1}`}.`)
        return
      }
    }

    const names = persons.map((person) => person.name.trim().toLowerCase())
    if (new Set(names).size !== names.length) {
      setError('Each person needs a unique name.')
      return
    }

    setUploading(true)

    try {
      await axios.delete(`${API}/selfies`)

      for (const person of persons) {
        const formData = new FormData()
        formData.append('file', person.blob, person.blob.name || 'selfie.jpg')
        formData.append('name', person.name.trim())
        await axios.post(`${API}/selfie`, formData)
      }

      onUploaded(persons.map((person) => ({
        name: person.name.trim(),
        previewUrl: person.previewUrl,
      })))
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed. Make sure the backend is running.')
      setUploading(false)
    }
  }

  const allReady = persons.every((person) => person.name.trim() && person.blob)

  return (
    <section className="selfie-wrap">
      {mode === 'webcam' && (
        <div className="webcam-modal">
          <div className="webcam-modal-inner">
            <div className="modal-topline">
              <span>Capture face photo</span>
              <strong>{persons[activePerson]?.name || `Person ${activePerson + 1}`}</strong>
            </div>
            <div className="webcam-frame">
              <video ref={videoRef} autoPlay playsInline muted className="webcam-video" />
              <div className="face-guide" />
            </div>
            <div className="webcam-actions">
              <button className="btn-secondary" onClick={() => { stopWebcam(); setMode(null) }}>Cancel</button>
              <button className="btn-capture" onClick={captureWebcam} disabled={!streaming} aria-label="Capture photo">
                <span />
              </button>
              <div className="modal-spacer" />
            </div>
          </div>
        </div>
      )}

      <div className="workflow-card">
        <div className="screen-heading">
          <p className="eyebrow">Step 1</p>
          <h1>Add the people to find</h1>
          <p>Use clear, front-facing photos. TripFace will compare these faces against your selected Drive folder.</p>
        </div>

        <div className="persons-list">
          {persons.map((person, index) => (
            <article key={index} className="person-card">
              <div className="person-card-header">
                <div>
                  <span className="person-num">Person {index + 1}</span>
                  <input
                    className="name-input"
                    placeholder={index === 0 ? 'Name, e.g. Rahul' : 'Name, e.g. Priya'}
                    value={person.name}
                    onChange={(event) => updatePerson(index, { name: event.target.value })}
                  />
                </div>
                {persons.length > 1 && (
                  <button className="icon-button danger" onClick={() => removePerson(index)} aria-label="Remove person">
                    ×
                  </button>
                )}
              </div>

              {!person.previewUrl ? (
                <div className="photo-options">
                  <button className="photo-opt-btn" onClick={() => startWebcam(index)}>
                    <span className="opt-icon">CAM</span>
                    <span>Webcam</span>
                  </button>
                  <button className="photo-opt-btn" onClick={() => openMobileCamera(index)}>
                    <span className="opt-icon">MOB</span>
                    <span>Camera</span>
                  </button>
                  <button className="photo-opt-btn" onClick={() => openGallery(index)}>
                    <span className="opt-icon">IMG</span>
                    <span>Gallery</span>
                  </button>
                </div>
              ) : (
                <div className="photo-preview-row">
                  <img src={person.previewUrl} alt={person.name || `Person ${index + 1}`} className="person-preview" />
                  <div className="preview-meta">
                    <strong>Photo ready</strong>
                    <span>Face source added for matching</span>
                  </div>
                  <button className="btn-secondary compact" onClick={() => clearPhoto(index)}>Replace</button>
                </div>
              )}
            </article>
          ))}
        </div>

        {persons.length < MAX_PERSONS && (
          <button className="btn-add-person" onClick={addPerson}>
            Add second person
          </button>
        )}

        {error && <div className="error-box">{error}</div>}

        <div className="footer-actions">
          <div className="privacy-note">Matching runs through your local backend.</div>
          <button className="btn-primary" onClick={handleUploadAll} disabled={!allReady || uploading}>
            {uploading ? <><span className="spinner" /> Processing</> : 'Continue to folder'}
          </button>
        </div>

        <input ref={fileInputRef} type="file" accept="image/*" onChange={handleFileChange} hidden />
        <canvas ref={canvasRef} hidden />
      </div>
    </section>
  )
}
