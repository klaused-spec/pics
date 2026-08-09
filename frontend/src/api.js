import axios from 'axios'

// Detecta dinamicamente o host do backend
// - Em dev (localhost:5173 / IP:5173) → usa o backend direto na porta 8000 (HTTP)
// - Em produção (servido pelo reverse proxy Caddy em HTTPS) → usa /api na
//   MESMA origem, e o proxy encaminha para o backend. Evita mixed-content e
//   não expõe a porta 8000.
const getBaseURL = () => {
  const { hostname, port } = window.location

  // Dev local direto no Vite (porta 5173) ou acesso por IP na 5173
  if ((hostname === 'localhost' || hostname === '127.0.0.1') && port === '5173') {
    return 'http://localhost:8000/api'
  }
  if (port === '5173') {
    return `http://${hostname}:8000/api`
  }

  // Produção atrás do reverse proxy (HTTPS): mesma origem
  return '/api'
}

const apiRoot = getBaseURL()
console.log('Backend URL:', apiRoot)

export const api = axios.create({
  baseURL: apiRoot,
  withCredentials: true, // Importante para cookies/auth headers
})
const backendRoot = apiRoot.replace(/\/api$/, '')

// Interceptor para adicionar token JWT em todas as requisições
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Interceptor de resposta: 401 = sessão expirada → limpa token e redireciona para login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const isLoginEndpoint = error.config?.url?.includes('/auth/login')
      if (!isLoginEndpoint) {
        localStorage.removeItem('access_token')
        localStorage.removeItem('userEmail')
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// ===== AUTENTICAÇÃO =====
export const register = (email, password) => 
  api.post('/auth/register', { email, password })
  
export const login = (email, password) => 
  api.post('/auth/login', { email, password })
  
export const getCurrentUser = () => 
  api.get('/auth/me')

// ===== USUÁRIOS =====
export const getUsers = () => api.get('/auth/users')
export const createUser = (email, password) => api.post('/auth/users', { email, password })
export const updateUserPassword = (id, password) => api.put(`/auth/users/${id}/password`, { password })
export const deleteUser = (id) => api.delete(`/auth/users/${id}`)

export const logout = () => {
  localStorage.removeItem('access_token')
  localStorage.removeItem('userEmail')
}

// ===== MÍDIA =====
export const getMedia = (params) => api.get('/media', { params })
export const getMediaById = (id) => api.get(`/media/${id}`)
export const getMediaNeighbors = (id) => api.get(`/media/${id}/neighbors`)
export const searchMedia = (q, limit = 50) => api.get('/media/search', { params: { q, limit } })
export const getTimeline = (params) => api.get('/media/timeline', { params })
export const getStats = () => api.get('/media/stats')
export const getDuplicates = () => api.get('/media/duplicates')
export const deleteAllDuplicates = () => api.delete('/media/duplicates/all')

// Pessoas
export const getPersons = (params) => api.get('/persons/', { params })
export const createPerson = (name) => api.post('/persons/', { name })
export const updatePerson = (id, data) => api.put(`/persons/${id}`, data)
export const deletePerson = (id) => api.delete(`/persons/${id}`)
export const getPersonMedia = (personId, params) => api.get(`/persons/${personId}/media`, { params })
export const assignFace = (faceId, personId) => api.post(`/persons/faces/${faceId}/assign`, { person_id: personId })
export const unassignFace = (faceId) => api.post(`/persons/faces/${faceId}/unassign`)
export const confirmFace = (faceId) => api.post(`/persons/faces/${faceId}/confirm`)
export const ignoreFace = (faceId) => api.post(`/persons/faces/${faceId}/ignore`)
export const createManualFace = (mediaId, bbox) => api.post('/persons/faces/manual', { media_id: mediaId, ...bbox })
export const getPendingFaces = (params) => api.get('/persons/faces/pending', { params })
export const getFaceThumbnailUrl = (faceId, size = 120) => `${backendRoot}/api/persons/faces/${faceId}/thumbnail?size=${size}`
export const mergePersons = (keepId, mergeId) => api.post('/persons/merge', { keep_id: keepId, merge_id: mergeId })
export const runClustering = () => api.post('/persons/cluster')
export const getHighConfidenceFaces = (params) => api.get('/persons/faces/high-confidence', { params })
export const bulkApproveFaces = (faceIds) => api.post('/persons/faces/bulk-approve', { face_ids: faceIds })
export const bulkApproveAllFaces = (minConfidence = 0.75) => api.post('/persons/faces/bulk-approve-all', null, { params: { min_confidence: minConfidence } })
export const refreshFaceSuggestions = () => api.post('/persons/faces/refresh-suggestions')
export const cleanupLowConfidenceFaces = (minConfidence = 0.40) => api.post('/persons/cleanup', null, { params: { min_confidence: minConfidence } })

// Jobs
export const getJobs = (params) => api.get('/jobs/', { params })
export const startScan = () => api.post('/jobs/scan')
export const startAiProcessing = () => api.post('/jobs/ai-process', null, { params: { batch_size: 99999 } })
export const startFaceDetection = () => api.post('/jobs/face-detect', null, { params: { batch_size: 99999 } })
export const startFullPipeline = () => api.post('/jobs/full-pipeline')
export const startSync = () => api.post('/jobs/sync')
export const startPurgeMissing = () => api.post('/jobs/purge-missing')
export const backfillDimensions = () => api.post('/jobs/backfill-dimensions')
export const startRcloneDownload = () => api.post('/jobs/rclone-download')
export const getRcloneLog = () => api.get('/jobs/rclone-log')
export const databaseAudit = () => api.get('/jobs/audit')

// Álbuns
export const getAlbums = () => api.get('/albums/')
export const createAlbum = (name, description) => api.post('/albums/', { name, description })
export const getAlbum = (id) => api.get(`/albums/${id}`)
export const updateAlbum = (id, data) => api.put(`/albums/${id}`, data)
export const deleteAlbum = (id) => api.delete(`/albums/${id}`)
export const getAlbumMedia = (id, params) => api.get(`/albums/${id}/media`, { params })
export const addMediaToAlbum = (albumId, mediaIds) => api.post(`/albums/${albumId}/media`, { media_ids: mediaIds })
export const removeMediaFromAlbum = (albumId, mediaIds) => api.delete(`/albums/${albumId}/media`, { data: { media_ids: mediaIds } })
export const createFolderAndMoveMedia = (year, month, folderName, mediaIds) => api.post('/media/folders', { year, month, folder_name: folderName, media_ids: mediaIds })
export const bulkCorrectMediaDate = (data) => api.post('/media/bulk-date-correction', data)
export const startThumbnailWarmup = (size = 300) => api.post('/jobs/thumbnail-warmup', null, { params: { size } })
export const rebootServer = () => api.post('/jobs/reboot')
export const restartApp = () => api.post('/jobs/restart-app')
export const updateAndRestart = () => api.post('/jobs/update-and-restart')
export const deleteJob = (jobId) => api.delete(`/jobs/${jobId}`)
export const deleteAllJobs = (force = false) => api.delete('/jobs/', { params: { force } })
export const resumeInterruptedJobs = () => api.post('/jobs/resume-interrupted')
export const resumeJob = (jobId) => api.post(`/jobs/${jobId}/resume`)

// URLs de mídia
export const getThumbnailUrl = (id, size = 300) => `${backendRoot}/api/media/${id}/thumbnail?size=${size}`
export const getFileUrl = (id) => `${backendRoot}/api/media/${id}/file`
export const getStreamUrl = (id) => {
  const token = localStorage.getItem('access_token')
  return `${backendRoot}/api/media/${id}/stream${token ? `?token=${encodeURIComponent(token)}` : ''}`
}
export const forceTranscode = (id) => api.post(`/media/${id}/transcode`)
export const getTranscodeStatus = (id) => api.get(`/media/${id}/transcode-status`)
export const deleteOriginalVideo = (id) => api.delete(`/media/${id}/original`)
export const deleteMedia = (id) => api.delete(`/media/${id}`)

// Settings
export const getSettings = () => api.get('/settings/paths')
export const updateSettings = (data) => api.put('/settings/paths', data)
export const backupDatabase = () => api.get('/settings/backup', { responseType: 'blob' })
export const restoreDatabase = (file) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/settings/restore', form)
}

// Mobile
export const getMobileApks = () => api.get('/mobile/apks')
export const getMobileApkUrl = (filename) => `${backendRoot}/api/mobile/apks/${encodeURIComponent(filename)}`
export const listMusic = () => api.get('/music')
export const uploadMusic = (file) => {
  const fd = new FormData(); fd.append('file', file)
  return api.post('/music/upload', fd)
}
export const deleteMusic = (filename) => api.delete(`/music/${encodeURIComponent(filename)}`)
export const getMusicUrl = (filename) => `${backendRoot}/api/music/stream/${encodeURIComponent(filename)}`

// Logs
export const getWorkerLogs = () => api.get('/logs/workers')
export const getWorkerLog = (name, n = 300) => api.get(`/logs/worker/${encodeURIComponent(name)}`, { params: { n } })
export const getLogsStreamUrl = () => {
  const token = localStorage.getItem('access_token')
  return `${backendRoot}/api/logs/stream${token ? `?token=${encodeURIComponent(token)}` : ''}`
}

// Slideshow render
export const startSlideshowRender = (payload) => api.post('/slideshow-render/start', payload)
export const getSlideshowRenderStatus = (slug) => api.get(`/slideshow-render/status/${slug}`)
export const listSlideshowRenders = () => api.get('/slideshow-render/list')
export const deleteSlideshowRender = (slug) => api.delete(`/slideshow-render/${slug}`)
export const getSlideshowStreamUrl = (slug) => {
  const token = localStorage.getItem('token')
  return `${backendRoot}/api/slideshow-render/stream/${slug}${token ? `?token=${encodeURIComponent(token)}` : ''}`
}
export default api
