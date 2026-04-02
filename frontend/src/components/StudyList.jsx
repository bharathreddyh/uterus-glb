import React, { useEffect, useState, useCallback } from 'react'
import { getStudies, deleteStudy } from '../api.js'

function formatDate(dateStr) {
  if (!dateStr || dateStr.length < 8) return dateStr || '—'
  return `${dateStr.slice(6, 8)}/${dateStr.slice(4, 6)}/${dateStr.slice(0, 4)}`
}

function isNew(receivedAt) {
  if (!receivedAt) return false
  const diff = Date.now() - new Date(receivedAt + 'Z').getTime()
  return diff < 5 * 60 * 1000 // 5 minutes
}

export default function StudyList({ selectedUid, onSelect, onDeleted, refreshTick }) {
  const [studies, setStudies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [dicomOnline, setDicomOnline] = useState(false)

  const fetchStudies = useCallback(async () => {
    try {
      const data = await getStudies()
      setStudies(data)
      setError(null)
    } catch (e) {
      setError('Failed to load studies')
    } finally {
      setLoading(false)
    }
  }, [])

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch('/api/health')
      if (res.ok) {
        const data = await res.json()
        setDicomOnline(data.dicom_receiver_running === true)
      } else {
        setDicomOnline(false)
      }
    } catch {
      setDicomOnline(false)
    }
  }, [])

  useEffect(() => {
    fetchStudies()
    checkHealth()
  }, [fetchStudies, checkHealth, refreshTick])

  // Auto-refresh every 10 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchStudies()
      checkHealth()
    }, 10000)
    return () => clearInterval(interval)
  }, [fetchStudies, checkHealth])

  const handleDelete = async (e, uid) => {
    e.stopPropagation()
    if (!window.confirm('Delete this study and all its images/report?')) return
    try {
      await deleteStudy(uid)
      setStudies((prev) => prev.filter((s) => s.study_instance_uid !== uid))
      onDeleted?.(uid)
    } catch (err) {
      alert('Failed to delete: ' + err.message)
    }
  }

  const filtered = studies.filter((s) => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      (s.patient_name || '').toLowerCase().includes(q) ||
      (s.patient_id || '').toLowerCase().includes(q) ||
      (s.study_date || '').includes(q)
    )
  })

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">Uterus GLB</div>
        <div className="sidebar-subtitle">USG Typist</div>
        <div className="sidebar-status">
          <span className={`status-dot ${dicomOnline ? 'online' : 'offline'}`} />
          <span>DICOM SCP {dicomOnline ? 'online :11112' : 'offline'}</span>
        </div>
      </div>

      <div className="sidebar-search">
        <input
          type="text"
          placeholder="Search patient..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="study-list">
        {loading && (
          <div className="study-empty">Loading studies...</div>
        )}
        {!loading && error && (
          <div className="study-empty" style={{ color: '#e07070' }}>{error}</div>
        )}
        {!loading && !error && filtered.length === 0 && (
          <div className="study-empty">
            {search ? 'No studies match search' : 'No studies yet.\nSend DICOM to port 11112.'}
          </div>
        )}
        {filtered.map((study, idx) => {
          const uid = study.study_instance_uid
          const selected = uid === selectedUid
          const fresh = isNew(study.received_at)

          return (
            <React.Fragment key={uid}>
              <div
                className={`study-item ${selected ? 'selected' : ''}`}
                onClick={() => onSelect(study)}
              >
                <div className="study-item-name">
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {study.patient_name || 'Unknown'}
                  </span>
                  {fresh && <span className="badge-new">NEW</span>}
                </div>
                <div className="study-item-meta">
                  <span>{study.patient_id ? `ID: ${study.patient_id}` : 'No ID'}</span>
                  <span>{formatDate(study.study_date)}</span>
                  <span className="badge-images">{study.num_images} img</span>
                  <button
                    className="delete-btn"
                    onClick={(e) => handleDelete(e, uid)}
                    title="Delete study"
                  >
                    ✕
                  </button>
                </div>
              </div>
              {idx < filtered.length - 1 && <div className="study-item-divider" />}
            </React.Fragment>
          )
        })}
      </div>
    </div>
  )
}
