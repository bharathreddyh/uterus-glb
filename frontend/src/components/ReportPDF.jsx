/**
 * ReportPDF.jsx
 * PDF generation for USG reports using jsPDF + jspdf-autotable.
 * Exports: generate(study, report, imageDataUrl?) -> blobUrl
 *          downloadPDF(study, report, imageDataUrl?)
 */

function formatDate(dateStr) {
  if (!dateStr) return ''
  // DICOM date: YYYYMMDD
  if (/^\d{8}$/.test(dateStr)) {
    return `${dateStr.slice(6, 8)}/${dateStr.slice(4, 6)}/${dateStr.slice(0, 4)}`
  }
  // ISO date: YYYY-MM-DD
  if (/^\d{4}-\d{2}-\d{2}/.test(dateStr)) {
    const [y, m, d] = dateStr.split('-')
    return `${d}/${m}/${y}`
  }
  return dateStr
}

function capitalize(str) {
  if (!str) return ''
  return str.charAt(0).toUpperCase() + str.slice(1)
}

function formatGA(weeks, days) {
  if (weeks == null && days == null) return ''
  const w = weeks != null ? `${weeks}w` : ''
  const d = days != null ? ` ${days}d` : ''
  return (w + d).trim()
}

export async function generate(study, report, imageDataUrl = null) {
  const { jsPDF } = await import('jspdf')
  await import('jspdf-autotable')

  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
  const pageW = doc.internal.pageSize.getWidth()
  const pageH = doc.internal.pageSize.getHeight()
  const margin = 15
  const contentW = pageW - margin * 2

  let y = margin

  // ── Header ────────────────────────────────────────────────────────────
  doc.setFillColor(0, 51, 102)
  doc.rect(0, 0, pageW, 28, 'F')

  doc.setTextColor(255, 255, 255)
  doc.setFontSize(16)
  doc.setFont('helvetica', 'bold')
  doc.text('IHA CARE ULTRASOUND CENTER', pageW / 2, 11, { align: 'center' })

  doc.setFontSize(9)
  doc.setFont('helvetica', 'normal')
  doc.text('Obstetric & Gynaecological Ultrasound Services', pageW / 2, 18, { align: 'center' })
  doc.text('Tel: —   |   Email: —   |   www.ihacare.local', pageW / 2, 23, { align: 'center' })

  y = 34
  doc.setTextColor(0, 0, 0)

  // ── Report meta row ──────────────────────────────────────────────────
  doc.setFontSize(8)
  doc.setFont('helvetica', 'normal')
  doc.setTextColor(100)
  const reportDate = report.created_at
    ? formatDate(report.created_at.slice(0, 10))
    : formatDate(new Date().toISOString().slice(0, 10))
  const reportId = report.id ? `RPT-${String(report.id).padStart(5, '0')}` : 'DRAFT'
  doc.text(`Report No: ${reportId}`, margin, y)
  doc.text(`Date: ${reportDate}`, pageW - margin, y, { align: 'right' })
  y += 5

  // Divider
  doc.setDrawColor(0, 51, 102)
  doc.setLineWidth(0.5)
  doc.line(margin, y, pageW - margin, y)
  y += 4

  // ── Scan type banner ─────────────────────────────────────────────────
  doc.setFontSize(11)
  doc.setFont('helvetica', 'bold')
  doc.setTextColor(0, 51, 102)
  doc.text('OBSTETRIC ULTRASOUND REPORT', pageW / 2, y + 4, { align: 'center' })
  y += 10

  // ── Patient details table ────────────────────────────────────────────
  doc.setTextColor(0)
  doc.autoTable({
    startY: y,
    margin: { left: margin, right: margin },
    tableWidth: contentW,
    styles: { fontSize: 9, cellPadding: 2.5 },
    headStyles: { fillColor: [230, 240, 255], textColor: [0, 51, 102], fontStyle: 'bold', fontSize: 8 },
    columnStyles: {
      0: { fontStyle: 'bold', cellWidth: contentW * 0.25 },
      1: { cellWidth: contentW * 0.25 },
      2: { fontStyle: 'bold', cellWidth: contentW * 0.25 },
      3: { cellWidth: contentW * 0.25 },
    },
    body: [
      ['Patient Name', report.patient_name || study.patient_name || '—',
       'Patient ID', study.patient_id || '—'],
      ['Age', report.patient_age || '—',
       'Sex', capitalize(study.patient_sex) || '—'],
      ['Study Date', formatDate(study.study_date),
       'Modality', study.modality || 'US'],
      ['Referring Doctor', report.referring_doctor || '—',
       'Radiologist', report.radiologist || '—'],
    ],
    theme: 'grid',
  })

  y = doc.lastAutoTable.finalY + 6

  // ── Fetal Measurements Table ─────────────────────────────────────────
  const m = report.measurements || {}

  doc.setFontSize(9)
  doc.setFont('helvetica', 'bold')
  doc.setTextColor(0, 51, 102)
  doc.text('FETAL BIOMETRY', margin, y)
  y += 3

  const measRows = [
    ['BPD (Biparietal Diameter)', m.bpd != null ? `${m.bpd} mm` : '—', 'Varies with GA'],
    ['HC (Head Circumference)', m.hc != null ? `${m.hc} mm` : '—', 'Varies with GA'],
    ['AC (Abdominal Circumference)', m.ac != null ? `${m.ac} mm` : '—', 'Varies with GA'],
    ['FL (Femur Length)', m.fl != null ? `${m.fl} mm` : '—', 'Varies with GA'],
    ['EFW (Estimated Fetal Weight)', m.efw != null ? `${m.efw} g` : '—', 'Hadlock formula'],
    ['AFI (Amniotic Fluid Index)', m.afi != null ? `${m.afi} cm` : '—', '5–25 cm'],
    ['Gestational Age', formatGA(m.ga_weeks, m.ga_days) || '—', ''],
    ['EDD by LMP', m.edd_by_lmp ? formatDate(m.edd_by_lmp) : '—', ''],
    ['EDD by Scan', m.edd_by_scan ? formatDate(m.edd_by_scan) : '—', ''],
  ]

  doc.autoTable({
    startY: y,
    margin: { left: margin, right: margin },
    tableWidth: contentW,
    head: [['Parameter', 'Measurement', 'Reference']],
    body: measRows,
    styles: { fontSize: 9, cellPadding: 2.5 },
    headStyles: { fillColor: [0, 51, 102], textColor: 255, fontStyle: 'bold', fontSize: 8 },
    columnStyles: {
      0: { cellWidth: contentW * 0.5 },
      1: { cellWidth: contentW * 0.25, halign: 'center' },
      2: { cellWidth: contentW * 0.25, textColor: [100, 100, 100] },
    },
    theme: 'striped',
    alternateRowStyles: { fillColor: [248, 251, 255] },
  })

  y = doc.lastAutoTable.finalY + 6

  // ── Additional Findings ──────────────────────────────────────────────
  const additionalRows = []
  if (m.placenta_location) additionalRows.push(['Placenta Location', capitalize(m.placenta_location)])
  if (m.amniotic_fluid) additionalRows.push(['Amniotic Fluid', capitalize(m.amniotic_fluid)])
  if (m.presentation) additionalRows.push(['Fetal Presentation', capitalize(m.presentation)])
  if (m.fetal_heart_rate) additionalRows.push(['Fetal Heart Rate', `${m.fetal_heart_rate} bpm`])

  if (additionalRows.length > 0) {
    doc.setFontSize(9)
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(0, 51, 102)
    doc.text('ADDITIONAL FINDINGS', margin, y)
    y += 3

    doc.autoTable({
      startY: y,
      margin: { left: margin, right: margin },
      tableWidth: contentW,
      body: additionalRows,
      styles: { fontSize: 9, cellPadding: 2.5 },
      columnStyles: {
        0: { fontStyle: 'bold', cellWidth: contentW * 0.5 },
        1: { cellWidth: contentW * 0.5 },
      },
      theme: 'plain',
    })

    y = doc.lastAutoTable.finalY + 6
  }

  // ── Impression ───────────────────────────────────────────────────────
  if (report.impression) {
    // Check if need new page
    if (y > pageH - 60) {
      doc.addPage()
      y = margin
    }

    doc.setFontSize(9)
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(0, 51, 102)
    doc.text('IMPRESSION', margin, y)
    y += 4

    doc.setFont('helvetica', 'normal')
    doc.setTextColor(0)
    doc.setFontSize(9)

    const lines = doc.splitTextToSize(report.impression, contentW)
    doc.text(lines, margin, y)
    y += lines.length * 4.5 + 4
  }

  // ── Advice ───────────────────────────────────────────────────────────
  if (report.advice) {
    if (y > pageH - 50) {
      doc.addPage()
      y = margin
    }

    doc.setFontSize(9)
    doc.setFont('helvetica', 'bold')
    doc.setTextColor(0, 51, 102)
    doc.text('ADVICE / RECOMMENDATIONS', margin, y)
    y += 4

    doc.setFont('helvetica', 'normal')
    doc.setTextColor(0)
    doc.setFontSize(9)

    const lines = doc.splitTextToSize(report.advice, contentW)
    doc.text(lines, margin, y)
    y += lines.length * 4.5 + 8
  }

  // ── Signature ────────────────────────────────────────────────────────
  if (y > pageH - 40) {
    doc.addPage()
    y = margin + 10
  }

  const sigY = Math.max(y + 10, pageH - 45)
  doc.setDrawColor(150)
  doc.setLineWidth(0.3)
  doc.line(pageW - margin - 60, sigY, pageW - margin, sigY)
  doc.setFontSize(8)
  doc.setFont('helvetica', 'normal')
  doc.setTextColor(80)
  doc.text(report.radiologist || 'Radiologist', pageW - margin - 30, sigY + 4, { align: 'center' })
  doc.text('Signature & Stamp', pageW - margin - 30, sigY + 8, { align: 'center' })

  // ── Footer ────────────────────────────────────────────────────────────
  const footerY = pageH - 10
  doc.setFontSize(7)
  doc.setTextColor(140)
  doc.setFont('helvetica', 'italic')
  doc.text(
    'This report is confidential and intended solely for the referred physician. Clinical correlation is advised.',
    pageW / 2,
    footerY,
    { align: 'center' }
  )

  // ── Page numbers ─────────────────────────────────────────────────────
  const totalPages = doc.internal.getNumberOfPages()
  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i)
    doc.setFontSize(7)
    doc.setTextColor(140)
    doc.setFont('helvetica', 'normal')
    doc.text(`Page ${i} of ${totalPages}`, pageW - margin, pageH - 10, { align: 'right' })
  }

  const blob = doc.output('blob')
  return URL.createObjectURL(blob)
}

export async function downloadPDF(study, report, imageDataUrl = null) {
  const url = await generate(study, report, imageDataUrl)
  const a = document.createElement('a')
  a.href = url
  const patName = (report.patient_name || study.patient_name || 'report').replace(/[^a-zA-Z0-9]/g, '_')
  const dateStr = (study.study_date || '').slice(0, 8) || new Date().toISOString().slice(0, 10).replace(/-/g, '')
  a.download = `USG_${patName}_${dateStr}.pdf`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 10000)
}

// Default export so it can be imported as a module too
export default { generate, downloadPDF }
