const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw Object.assign(new Error(err.detail || 'Request failed'), { status: res.status })
  }
  if (res.status === 204) return null
  return res.json()
}

export function getStudies() {
  return request('/studies')
}

export function getStudy(uid) {
  return request(`/studies/${encodeURIComponent(uid)}`)
}

export function deleteStudy(uid) {
  return request(`/studies/${encodeURIComponent(uid)}`, { method: 'DELETE' })
}

export async function getImages(studyUid) {
  const detail = await getStudy(studyUid)
  return detail.images || []
}

export function getReport(studyUid) {
  return request(`/reports/${encodeURIComponent(studyUid)}`)
}

export function createReport(studyUid, data) {
  return request(`/reports/${encodeURIComponent(studyUid)}`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateReport(studyUid, data) {
  return request(`/reports/${encodeURIComponent(studyUid)}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function getReportPdfData(studyUid) {
  return request(`/reports/${encodeURIComponent(studyUid)}/pdf-data`)
}

export function getDicomUrl(imageUid) {
  return `/images/${encodeURIComponent(imageUid)}/dicom`
}

export function getJpegUrl(imageUid) {
  return `/images/${encodeURIComponent(imageUid)}/jpeg`
}

export function getFrameUrl(imageUid, frame = 0) {
  return `/images/${encodeURIComponent(imageUid)}/frames?frame=${frame}`
}
