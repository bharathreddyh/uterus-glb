import React, { useEffect, useRef, useState, useCallback } from 'react'
import { getDicomUrl, getJpegUrl, getImages } from '../api.js'

// Cornerstone is loaded dynamically to avoid SSR issues and bundler complications.
// We use the JPEG frame endpoint as a reliable fallback viewer.

function formatDate(dateStr) {
  if (!dateStr || dateStr.length < 8) return dateStr || ''
  return `${dateStr.slice(6, 8)}/${dateStr.slice(4, 6)}/${dateStr.slice(0, 4)}`
}

export default function DicomViewer({ study }) {
  const [images, setImages] = useState([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [windowCenter, setWindowCenter] = useState(128)
  const [windowWidth, setWindowWidth] = useState(256)
  const [activeTool, setActiveTool] = useState('pan')
  const [imgSrc, setImgSrc] = useState(null)
  const [imgLoading, setImgLoading] = useState(false)

  const csInitialized = useRef(false)
  const csElement = useRef(null)
  const cornerstone = useRef(null)
  const cornerstoneWADO = useRef(null)
  const isDragging = useRef(false)
  const dragStart = useRef({ x: 0, y: 0, wc: 128, ww: 256 })
  const panStart = useRef({ x: 0, y: 0 })
  const csViewport = useRef(null)

  const studyUid = study?.study_instance_uid

  // Load image list
  useEffect(() => {
    if (!studyUid) return
    setLoading(true)
    setImages([])
    setCurrentIndex(0)

    getImages(studyUid)
      .then((imgs) => {
        setImages(imgs)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [studyUid])

  const currentImage = images[currentIndex] || null

  // Try to initialize Cornerstone
  useEffect(() => {
    if (csInitialized.current) return

    async function initCS() {
      try {
        const cs = await import('cornerstone-core')
        const csWADO = await import('cornerstone-wado-image-loader')

        csWADO.default.external.cornerstone = cs.default || cs
        if (typeof dicomParser !== 'undefined') {
          csWADO.default.external.dicomParser = dicomParser
        }

        cornerstone.current = cs.default || cs
        cornerstoneWADO.current = csWADO.default || csWADO
        csInitialized.current = true
      } catch (e) {
        // Cornerstone not available, fall back to JPEG rendering
        csInitialized.current = false
      }
    }

    initCS()
  }, [])

  // Render current image using JPEG frame endpoint (reliable fallback)
  useEffect(() => {
    if (!currentImage) {
      setImgSrc(null)
      return
    }
    setImgLoading(true)
    // Use the frame endpoint which renders DICOM pixel data server-side
    const url = `/images/${encodeURIComponent(currentImage.image_uid)}/frames?frame=0`
    setImgSrc(url)
  }, [currentImage])

  const handlePrev = () => setCurrentIndex((i) => Math.max(0, i - 1))
  const handleNext = () => setCurrentIndex((i) => Math.min(images.length - 1, i + 1))

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') handlePrev()
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') handleNext()
  }, [images.length]) // eslint-disable-line

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  // Mouse windowing (W/L drag when tool=window) and pan
  const handleMouseDown = (e) => {
    isDragging.current = true
    dragStart.current = { x: e.clientX, y: e.clientY, wc: windowCenter, ww: windowWidth }
    panStart.current = { x: e.clientX, y: e.clientY }
  }

  const handleMouseMove = (e) => {
    if (!isDragging.current) return
    const dx = e.clientX - dragStart.current.x
    const dy = e.clientY - dragStart.current.y

    if (activeTool === 'window') {
      setWindowCenter(Math.round(dragStart.current.wc + dy))
      setWindowWidth(Math.round(Math.max(1, dragStart.current.ww + dx)))
    }
  }

  const handleMouseUp = () => { isDragging.current = false }

  const handleWheel = (e) => {
    e.preventDefault()
    if (e.deltaY > 0) handleNext()
    else handlePrev()
  }

  const handleReset = () => {
    setWindowCenter(128)
    setWindowWidth(256)
  }

  if (loading) {
    return (
      <div className="viewer-layout">
        <div className="viewer-no-images">Loading images...</div>
      </div>
    )
  }

  if (images.length === 0) {
    return (
      <div className="viewer-layout">
        <div className="viewer-no-images">No images in this study</div>
      </div>
    )
  }

  const brightness = ((windowCenter - windowWidth / 2) / 255 * -50).toFixed(0)
  const contrast = (256 / Math.max(1, windowWidth) * 100).toFixed(0)

  return (
    <div className="viewer-layout">
      {/* Thumbnail strip */}
      <div className="viewer-thumbnails">
        {images.map((img, idx) => (
          <div
            key={img.image_uid}
            className={`thumb-item ${idx === currentIndex ? 'active' : ''}`}
            onClick={() => setCurrentIndex(idx)}
            title={`Image ${idx + 1}`}
          >
            <img
              src={getJpegUrl(img.image_uid)}
              alt={`Frame ${idx + 1}`}
              onError={(e) => { e.target.style.display = 'none' }}
            />
            <span className="thumb-item-num">{idx + 1}</span>
          </div>
        ))}
      </div>

      {/* Main viewer */}
      <div className="viewer-main">
        <div className="viewer-toolbar">
          <button
            className={`tool-btn ${activeTool === 'window' ? 'active' : ''}`}
            onClick={() => setActiveTool('window')}
            title="Drag to adjust Window/Level"
          >
            W/L
          </button>
          <button
            className={`tool-btn ${activeTool === 'pan' ? 'active' : ''}`}
            onClick={() => setActiveTool('pan')}
          >
            Pan
          </button>

          <label>
            WC:
            <input
              type="range"
              min="-1000"
              max="3000"
              value={windowCenter}
              onChange={(e) => setWindowCenter(Number(e.target.value))}
            />
            <span style={{ color: '#ccc', minWidth: 36, display: 'inline-block' }}>
              {windowCenter}
            </span>
          </label>

          <label>
            WW:
            <input
              type="range"
              min="1"
              max="4000"
              value={windowWidth}
              onChange={(e) => setWindowWidth(Number(e.target.value))}
            />
            <span style={{ color: '#ccc', minWidth: 36, display: 'inline-block' }}>
              {windowWidth}
            </span>
          </label>

          <button className="tool-btn" onClick={handleReset}>Reset</button>

          <div style={{ flex: 1 }} />

          <button
            className="nav-btn"
            onClick={handlePrev}
            disabled={currentIndex === 0}
          >
            ◀ Prev
          </button>
          <span style={{ color: '#aaa', fontSize: 12 }}>
            {currentIndex + 1} / {images.length}
          </span>
          <button
            className="nav-btn"
            onClick={handleNext}
            disabled={currentIndex === images.length - 1}
          >
            Next ▶
          </button>
        </div>

        <div
          className="viewer-canvas-wrap"
          style={{ cursor: activeTool === 'window' ? 'crosshair' : 'grab' }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onWheel={handleWheel}
        >
          {imgSrc && (
            <img
              key={imgSrc}
              src={imgSrc}
              alt={`DICOM image ${currentIndex + 1}`}
              onLoad={() => setImgLoading(false)}
              onError={() => setImgLoading(false)}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                display: 'block',
                filter: `brightness(${100 + Number(brightness)}%) contrast(${contrast}%)`,
                userSelect: 'none',
                pointerEvents: 'none',
              }}
              draggable={false}
            />
          )}

          {imgLoading && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
              color: '#555', fontSize: 13,
            }}>
              Loading...
            </div>
          )}

          {/* Overlay: patient info top-left */}
          {currentImage && (
            <div className="viewer-overlay">
              <div>{study.patient_name || 'Unknown'}</div>
              <div>{study.patient_id ? `ID: ${study.patient_id}` : ''}</div>
              <div>{formatDate(study.study_date)}</div>
              <div>{study.modality || 'US'}</div>
            </div>
          )}

          {/* Overlay: image number bottom-right */}
          {currentImage && (
            <div className="viewer-overlay-br">
              <div>WC: {windowCenter} / WW: {windowWidth}</div>
              <div>
                Im: {currentIndex + 1}/{images.length}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
