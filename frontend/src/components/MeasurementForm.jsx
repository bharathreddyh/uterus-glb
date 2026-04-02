import React, { useState, useEffect, useRef, useCallback } from 'react'
import { getReport, createReport, updateReport } from '../api.js'
import { downloadPDF } from './ReportPDF.jsx'

// ── Hadlock EFW formula ──────────────────────────────────────────────────
// log10(EFW) = 1.3596 + 0.0064*HC + 0.0424*AC + 0.174*FL + 0.00061*BPD*AC - 0.00386*AC*FL
function calcEFW(bpd, hc, ac, fl) {
  if (!bpd || !hc || !ac || !fl) return null
  const b = Number(bpd), h = Number(hc), a = Number(ac), f = Number(fl)
  if (!b || !h || !a || !f) return null
  const log10efw = 1.3596 + 0.0064 * h + 0.0424 * a + 0.174 * f + 0.00061 * b * a - 0.00386 * a * f
  return Math.round(Math.pow(10, log10efw))
}

// GA from FL (Hadlock simplified): GA_weeks = FL * 0.2459 + 8.788
function calcGAFromFL(fl) {
  if (!fl) return null
  const totalWeeks = Number(fl) * 0.2459 + 8.788
  const weeks = Math.floor(totalWeeks)
  const days = Math.round((totalWeeks - weeks) * 7)
  return { weeks, days }
}

// EDD from LMP string (YYYY-MM-DD)
function calcEDDFromLMP(lmp) {
  if (!lmp) return ''
  try {
    const d = new Date(lmp)
    if (isNaN(d.getTime())) return ''
    d.setDate(d.getDate() + 280) // Naegele: LMP + 280 days
    return d.toISOString().slice(0, 10)
  } catch {
    return ''
  }
}

// EDD from GA (today's date, GA in weeks+days)
function calcEDDFromGA(gaWeeks, gaDays) {
  if (gaWeeks == null) return ''
  try {
    const totalDays = (gaWeeks * 7) + (gaDays || 0)
    const dueDate = new Date()
    dueDate.setDate(dueDate.getDate() + (280 - totalDays))
    return dueDate.toISOString().slice(0, 10)
  } catch {
    return ''
  }
}

const EMPTY_MEASUREMENTS = {
  bpd: '', hc: '', ac: '', fl: '', efw: '',
  afi: '',
  placenta_location: '',
  amniotic_fluid: '',
  presentation: '',
  fetal_heart_rate: '',
  edd_by_lmp: '',
  edd_by_scan: '',
  ga_weeks: '',
  ga_days: '',
}

function toFormMeasurements(m) {
  if (!m) return { ...EMPTY_MEASUREMENTS }
  return {
    bpd: m.bpd ?? '',
    hc: m.hc ?? '',
    ac: m.ac ?? '',
    fl: m.fl ?? '',
    efw: m.efw ?? '',
    afi: m.afi ?? '',
    placenta_location: m.placenta_location ?? '',
    amniotic_fluid: m.amniotic_fluid ?? '',
    presentation: m.presentation ?? '',
    fetal_heart_rate: m.fetal_heart_rate ?? '',
    edd_by_lmp: m.edd_by_lmp ?? '',
    edd_by_scan: m.edd_by_scan ?? '',
    ga_weeks: m.ga_weeks ?? '',
    ga_days: m.ga_days ?? '',
  }
}

export default function MeasurementForm({ study, onSaved }) {
  const [form, setForm] = useState({
    patient_name: study?.patient_name || '',
    patient_age: '',
    referring_doctor: '',
    radiologist: '',
    lmp_date: '',
    impression: '',
    advice: '',
    measurements: { ...EMPTY_MEASUREMENTS },
  })
  const [saveStatus, setSaveStatus] = useState('idle') // idle | saving | saved | error
  const [hasReport, setHasReport] = useState(false)
  const [pdfLoading, setPdfLoading] = useState(false)
  const autosaveTimer = useRef(null)
  const lastSavedRef = useRef(null)
  const studyUid = study?.study_instance_uid

  // Load existing report on mount / study change
  useEffect(() => {
    if (!studyUid) return
    setForm({
      patient_name: study?.patient_name || '',
      patient_age: '',
      referring_doctor: '',
      radiologist: '',
      lmp_date: '',
      impression: '',
      advice: '',
      measurements: { ...EMPTY_MEASUREMENTS },
    })
    setHasReport(false)
    setSaveStatus('idle')

    getReport(studyUid)
      .then((report) => {
        setHasReport(true)
        setForm({
          patient_name: report.patient_name || study?.patient_name || '',
          patient_age: report.patient_age || '',
          referring_doctor: report.referring_doctor || '',
          radiologist: report.radiologist || '',
          lmp_date: report.measurements?.edd_by_lmp
            ? ''
            : '',
          impression: report.impression || '',
          advice: report.advice || '',
          measurements: toFormMeasurements(report.measurements),
        })
      })
      .catch((e) => {
        if (e.status !== 404) console.error('Failed to load report:', e)
      })
  }, [studyUid]) // eslint-disable-line

  // Auto-calculate EFW when BPD/HC/AC/FL change
  useEffect(() => {
    const m = form.measurements
    const efw = calcEFW(m.bpd, m.hc, m.ac, m.fl)
    if (efw !== null) {
      setForm((prev) => ({
        ...prev,
        measurements: { ...prev.measurements, efw: String(efw) },
      }))
    }
  }, [form.measurements.bpd, form.measurements.hc, form.measurements.ac, form.measurements.fl]) // eslint-disable-line

  // Auto-calculate GA and EDD from FL
  useEffect(() => {
    const fl = form.measurements.fl
    if (!fl) return
    const ga = calcGAFromFL(fl)
    if (!ga) return
    const edd_by_scan = calcEDDFromGA(ga.weeks, ga.days)
    setForm((prev) => ({
      ...prev,
      measurements: {
        ...prev.measurements,
        ga_weeks: String(ga.weeks),
        ga_days: String(ga.days),
        edd_by_scan,
      },
    }))
  }, [form.measurements.fl]) // eslint-disable-line

  // Auto-calculate EDD from LMP
  useEffect(() => {
    if (!form.lmp_date) return
    const edd = calcEDDFromLMP(form.lmp_date)
    setForm((prev) => ({
      ...prev,
      measurements: { ...prev.measurements, edd_by_lmp: edd },
    }))
  }, [form.lmp_date])

  const buildPayload = useCallback(() => {
    const m = form.measurements
    const measurements = {}
    const numFields = ['bpd', 'hc', 'ac', 'fl', 'efw', 'afi', 'fetal_heart_rate', 'ga_weeks', 'ga_days']
    const strFields = ['placenta_location', 'amniotic_fluid', 'presentation', 'edd_by_lmp', 'edd_by_scan']

    for (const f of numFields) {
      const v = m[f]
      if (v !== '' && v != null) measurements[f] = Number(v)
    }
    for (const f of strFields) {
      if (m[f]) measurements[f] = m[f]
    }

    return {
      patient_name: form.patient_name,
      patient_age: form.patient_age,
      referring_doctor: form.referring_doctor,
      radiologist: form.radiologist,
      measurements,
      impression: form.impression,
      advice: form.advice,
    }
  }, [form])

  const doSave = useCallback(async (silent = false) => {
    if (!studyUid) return
    if (!silent) setSaveStatus('saving')

    try {
      const payload = buildPayload()
      if (hasReport) {
        await updateReport(studyUid, payload)
      } else {
        await createReport(studyUid, payload)
        setHasReport(true)
      }
      lastSavedRef.current = Date.now()
      if (!silent) {
        setSaveStatus('saved')
        onSaved?.()
        setTimeout(() => setSaveStatus('idle'), 3000)
      }
    } catch (e) {
      if (!silent) {
        setSaveStatus('error')
        setTimeout(() => setSaveStatus('idle'), 4000)
      }
      console.error('Save failed:', e)
    }
  }, [studyUid, hasReport, buildPayload, onSaved])

  // Auto-save every 30 seconds if form changed
  useEffect(() => {
    if (autosaveTimer.current) clearInterval(autosaveTimer.current)
    autosaveTimer.current = setInterval(() => {
      const since = lastSavedRef.current ? Date.now() - lastSavedRef.current : Infinity
      if (since > 25000) {
        doSave(true)
      }
    }, 30000)
    return () => clearInterval(autosaveTimer.current)
  }, [doSave])

  const setMeasurement = (key, value) => {
    setForm((prev) => ({
      ...prev,
      measurements: { ...prev.measurements, [key]: value },
    }))
  }

  const handleGeneratePDF = async () => {
    setPdfLoading(true)
    try {
      // Save first if needed
      await doSave(false)
      const { getReportPdfData } = await import('../api.js')
      const pdfData = await getReportPdfData(studyUid)
      await downloadPDF(pdfData.study, pdfData.report)
    } catch (e) {
      alert('PDF generation failed: ' + e.message)
    } finally {
      setPdfLoading(false)
    }
  }

  const m = form.measurements

  return (
    <div className="report-layout">
      {/* Patient Section */}
      <div className="form-card">
        <div className="form-card-title">Patient Information</div>
        <div className="form-grid">
          <div className="form-group">
            <label>Patient Name</label>
            <input
              type="text"
              value={form.patient_name}
              onChange={(e) => setForm((p) => ({ ...p, patient_name: e.target.value }))}
              placeholder="From DICOM"
            />
          </div>
          <div className="form-group">
            <label>Age</label>
            <input
              type="text"
              value={form.patient_age}
              onChange={(e) => setForm((p) => ({ ...p, patient_age: e.target.value }))}
              placeholder="e.g. 28 years"
            />
          </div>
          <div className="form-group">
            <label>LMP Date</label>
            <input
              type="date"
              value={form.lmp_date}
              onChange={(e) => setForm((p) => ({ ...p, lmp_date: e.target.value }))}
            />
          </div>
          <div className="form-group">
            <label>Referring Doctor</label>
            <input
              type="text"
              value={form.referring_doctor}
              onChange={(e) => setForm((p) => ({ ...p, referring_doctor: e.target.value }))}
              placeholder="Dr. Name"
            />
          </div>
          <div className="form-group">
            <label>Radiologist</label>
            <input
              type="text"
              value={form.radiologist}
              onChange={(e) => setForm((p) => ({ ...p, radiologist: e.target.value }))}
              placeholder="Dr. Name"
            />
          </div>
        </div>
      </div>

      {/* Fetal Measurements */}
      <div className="form-card">
        <div className="form-card-title">Fetal Biometry</div>
        <table className="measurements-table">
          <thead>
            <tr>
              <th style={{ width: '30%' }}>Parameter</th>
              <th style={{ width: '20%' }}>Value</th>
              <th style={{ width: '25%' }}>Unit</th>
              <th style={{ width: '25%' }}>Normal Range (ref)</th>
            </tr>
          </thead>
          <tbody>
            <MeasRow label="BPD (Biparietal Diameter)" value={m.bpd} unit="mm"
              onChange={(v) => setMeasurement('bpd', v)} normal="Varies with GA" />
            <MeasRow label="HC (Head Circumference)" value={m.hc} unit="mm"
              onChange={(v) => setMeasurement('hc', v)} normal="Varies with GA" />
            <MeasRow label="AC (Abdominal Circumference)" value={m.ac} unit="mm"
              onChange={(v) => setMeasurement('ac', v)} normal="Varies with GA" />
            <MeasRow label="FL (Femur Length)" value={m.fl} unit="mm"
              onChange={(v) => setMeasurement('fl', v)} normal="Varies with GA" />
            <tr>
              <td><strong>EFW (Estimated Fetal Weight)</strong></td>
              <td>
                <input
                  type="number"
                  value={m.efw}
                  onChange={(e) => setMeasurement('efw', e.target.value)}
                  placeholder="auto"
                  style={{ width: '100%', border: 'none', outline: 'none', fontStyle: m.efw ? 'normal' : 'italic', background: 'transparent' }}
                />
              </td>
              <td>grams</td>
              <td className="efw-calc">Hadlock formula</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* GA & Dating */}
      <div className="form-card">
        <div className="form-card-title">Gestational Age &amp; Dating</div>
        <div className="form-grid">
          <div className="form-group">
            <label>GA (Weeks)</label>
            <input
              type="number"
              value={m.ga_weeks}
              onChange={(e) => setMeasurement('ga_weeks', e.target.value)}
              placeholder="Auto from FL"
            />
          </div>
          <div className="form-group">
            <label>GA (Days)</label>
            <input
              type="number"
              value={m.ga_days}
              onChange={(e) => setMeasurement('ga_days', e.target.value)}
              placeholder="Auto from FL"
            />
          </div>
          <div className="form-group">
            <label>EDD by LMP</label>
            <input
              type="date"
              value={m.edd_by_lmp}
              onChange={(e) => setMeasurement('edd_by_lmp', e.target.value)}
              readOnly={!!form.lmp_date}
              title={form.lmp_date ? 'Auto-calculated from LMP' : ''}
            />
          </div>
          <div className="form-group">
            <label>EDD by Scan</label>
            <input
              type="date"
              value={m.edd_by_scan}
              onChange={(e) => setMeasurement('edd_by_scan', e.target.value)}
            />
          </div>
        </div>
      </div>

      {/* Additional Findings */}
      <div className="form-card">
        <div className="form-card-title">Additional Findings</div>
        <div className="form-grid">
          <div className="form-group">
            <label>AFI (Amniotic Fluid Index)</label>
            <input
              type="number"
              step="0.1"
              value={m.afi}
              onChange={(e) => setMeasurement('afi', e.target.value)}
              placeholder="cm"
            />
          </div>
          <div className="form-group">
            <label>Placenta Location</label>
            <select value={m.placenta_location} onChange={(e) => setMeasurement('placenta_location', e.target.value)}>
              <option value="">-- Select --</option>
              <option value="anterior">Anterior</option>
              <option value="posterior">Posterior</option>
              <option value="fundal">Fundal</option>
              <option value="lateral">Lateral</option>
              <option value="low-lying">Low-lying</option>
            </select>
          </div>
          <div className="form-group">
            <label>Amniotic Fluid</label>
            <select value={m.amniotic_fluid} onChange={(e) => setMeasurement('amniotic_fluid', e.target.value)}>
              <option value="">-- Select --</option>
              <option value="normal">Normal</option>
              <option value="polyhydramnios">Polyhydramnios</option>
              <option value="oligohydramnios">Oligohydramnios</option>
            </select>
          </div>
          <div className="form-group">
            <label>Presentation</label>
            <select value={m.presentation} onChange={(e) => setMeasurement('presentation', e.target.value)}>
              <option value="">-- Select --</option>
              <option value="cephalic">Cephalic</option>
              <option value="breech">Breech</option>
              <option value="transverse">Transverse</option>
              <option value="oblique">Oblique</option>
            </select>
          </div>
          <div className="form-group">
            <label>Fetal Heart Rate (bpm)</label>
            <input
              type="number"
              value={m.fetal_heart_rate}
              onChange={(e) => setMeasurement('fetal_heart_rate', e.target.value)}
              placeholder="bpm"
            />
          </div>
        </div>
      </div>

      {/* Report Text */}
      <div className="form-card">
        <div className="form-card-title">Report</div>
        <div className="form-grid">
          <div className="form-group form-row-full">
            <label>Impression</label>
            <textarea
              value={form.impression}
              onChange={(e) => setForm((p) => ({ ...p, impression: e.target.value }))}
              placeholder="Findings and impression..."
              rows={4}
            />
          </div>
          <div className="form-group form-row-full">
            <label>Advice / Recommendations</label>
            <textarea
              value={form.advice}
              onChange={(e) => setForm((p) => ({ ...p, advice: e.target.value }))}
              placeholder="Advice and follow-up recommendations..."
              rows={3}
            />
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="form-card">
        <div className="form-actions">
          <button
            className="btn btn-primary"
            onClick={() => doSave(false)}
            disabled={saveStatus === 'saving'}
          >
            {saveStatus === 'saving' ? 'Saving...' : hasReport ? 'Update Report' : 'Save Report'}
          </button>

          <button
            className="btn btn-success"
            onClick={handleGeneratePDF}
            disabled={pdfLoading || !hasReport}
            title={!hasReport ? 'Save report first' : 'Generate PDF report'}
          >
            {pdfLoading ? 'Generating...' : 'Download PDF'}
          </button>

          <div className={`save-status ${saveStatus === 'saved' ? 'saved' : saveStatus === 'saving' ? 'saving' : saveStatus === 'error' ? 'error' : ''}`}>
            {saveStatus === 'saved' && '✓ Saved'}
            {saveStatus === 'saving' && 'Saving...'}
            {saveStatus === 'error' && '✗ Save failed'}
            {saveStatus === 'idle' && lastSavedRef.current && (
              <span style={{ color: '#999', fontSize: 11 }}>
                Last saved {new Date(lastSavedRef.current).toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function MeasRow({ label, value, unit, onChange, normal }) {
  return (
    <tr>
      <td>{label}</td>
      <td>
        <input
          type="number"
          step="0.1"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          style={{ width: '100%', border: 'none', outline: 'none', background: 'transparent' }}
          placeholder="—"
        />
      </td>
      <td>{unit}</td>
      <td className="normal-range">{normal}</td>
    </tr>
  )
}
