import React, { useState, useEffect, useRef, useCallback } from 'react'
import StudyList from './components/StudyList.jsx'
import DicomViewer from './components/DicomViewer.jsx'
import MeasurementForm from './components/MeasurementForm.jsx'

function Toast({ toasts, onDismiss }) {
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div key={t.id} className="toast" onClick={() => onDismiss(t.id)}>
          <div className="toast-title">{t.title}</div>
          {t.sub && <div className="toast-sub">{t.sub}</div>}
        </div>
      ))}
    </div>
  )
}

export default function App() {
  const [selectedStudy, setSelectedStudy] = useState(null)
  const [activeTab, setActiveTab] = useState('viewer')
  const [toasts, setToasts] = useState([])
  const [refreshTick, setRefreshTick] = useState(0)
  const esRef = useRef(null)

  const addToast = useCallback((title, sub = '') => {
    const id = Date.now() + Math.random()
    setToasts((prev) => [...prev, { id, title, sub }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 5000)
  }, [])

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  // SSE connection for real-time notifications
  useEffect(() => {
    let retryTimeout = null

    function connect() {
      const es = new EventSource('/events')
      esRef.current = es

      es.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data)
          if (data.type === 'new_study') {
            addToast(
              'New study received',
              data.patient_name ? `Patient: ${data.patient_name}` : data.study_uid
            )
            setRefreshTick((n) => n + 1)
          }
        } catch (_) {}
      }

      es.onerror = () => {
        es.close()
        esRef.current = null
        retryTimeout = setTimeout(connect, 5000)
      }
    }

    connect()

    return () => {
      clearTimeout(retryTimeout)
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [addToast])

  const handleStudySelect = (study) => {
    setSelectedStudy(study)
    setActiveTab('viewer')
  }

  const handleStudyDeleted = (uid) => {
    if (selectedStudy?.study_instance_uid === uid) {
      setSelectedStudy(null)
    }
    setRefreshTick((n) => n + 1)
  }

  return (
    <div className="app-layout">
      <StudyList
        selectedUid={selectedStudy?.study_instance_uid}
        onSelect={handleStudySelect}
        onDeleted={handleStudyDeleted}
        refreshTick={refreshTick}
      />

      <div className="main-content">
        {selectedStudy ? (
          <>
            <div className="main-header">
              <div>
                <div className="main-header-title">
                  {selectedStudy.patient_name || 'Unknown Patient'}
                </div>
                <div className="main-header-meta">
                  ID: {selectedStudy.patient_id || '—'} &nbsp;|&nbsp;
                  Date: {formatDate(selectedStudy.study_date)} &nbsp;|&nbsp;
                  {selectedStudy.modality || 'US'} &nbsp;|&nbsp;
                  {selectedStudy.num_images} image{selectedStudy.num_images !== 1 ? 's' : ''}
                </div>
              </div>
            </div>

            <div className="tabs">
              <button
                className={`tab-btn ${activeTab === 'viewer' ? 'active' : ''}`}
                onClick={() => setActiveTab('viewer')}
              >
                DICOM Viewer
              </button>
              <button
                className={`tab-btn ${activeTab === 'report' ? 'active' : ''}`}
                onClick={() => setActiveTab('report')}
              >
                Report / Measurements
              </button>
            </div>

            <div className="tab-content">
              {activeTab === 'viewer' && (
                <DicomViewer study={selectedStudy} />
              )}
              {activeTab === 'report' && (
                <MeasurementForm
                  study={selectedStudy}
                  onSaved={() => addToast('Report saved', selectedStudy.patient_name)}
                />
              )}
            </div>
          </>
        ) : (
          <div className="empty-state">
            <div className="empty-state-icon">🩻</div>
            <div className="empty-state-text">No study selected</div>
            <div className="empty-state-sub">
              Select a study from the sidebar, or send DICOM images to port 11112
            </div>
          </div>
        )}
      </div>

      <Toast toasts={toasts} onDismiss={dismissToast} />
    </div>
  )
}

function formatDate(dateStr) {
  if (!dateStr || dateStr.length < 8) return dateStr || '—'
  // YYYYMMDD -> DD/MM/YYYY
  return `${dateStr.slice(6, 8)}/${dateStr.slice(4, 6)}/${dateStr.slice(0, 4)}`
}
