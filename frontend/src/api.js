import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
})

// Mídia
export const getMedia = (params) => api.get('/media/', { params })
export const getMediaById = (id) => api.get(`/media/${id}`)
export const getMediaNeighbors = (id) => api.get(`/media/${id}/neighbors`)
export const searchMedia = (q, limit = 50) => api.get('/media/search', { params: { q, limit } })
export const getTimeline = () => api.get('/media/timeline')
export const getStats = () => api.get('/media/stats')

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
export const getFaceThumbnailUrl = (faceId, size = 120) => `/api/persons/faces/${faceId}/thumbnail?size=${size}`
export const mergePersons = (keepId, mergeId) => api.post('/persons/merge', { keep_id: keepId, merge_id: mergeId })
export const runClustering = () => api.post('/persons/cluster')

// Jobs
export const getJobs = (params) => api.get('/jobs/', { params })
export const startScan = () => api.post('/jobs/scan')
export const startAiProcessing = (batchSize = 10) => api.post('/jobs/ai-process', null, { params: { batch_size: batchSize } })
export const startFaceDetection = (batchSize = 10) => api.post('/jobs/face-detect', null, { params: { batch_size: batchSize } })
export const startFullPipeline = () => api.post('/jobs/full-pipeline')
export const startSync = () => api.post('/jobs/sync')

// Álbuns
export const getAlbums = () => api.get('/albums/')
export const createAlbum = (name, description) => api.post('/albums/', { name, description })
export const getAlbum = (id) => api.get(`/albums/${id}`)
export const updateAlbum = (id, data) => api.put(`/albums/${id}`, data)
export const deleteAlbum = (id) => api.delete(`/albums/${id}`)
export const getAlbumMedia = (id, params) => api.get(`/albums/${id}/media`, { params })
export const addMediaToAlbum = (albumId, mediaIds) => api.post(`/albums/${albumId}/media`, { media_ids: mediaIds })
export const removeMediaFromAlbum = (albumId, mediaIds) => api.delete(`/albums/${albumId}/media`, { data: { media_ids: mediaIds } })

// URLs de mídia
export const getThumbnailUrl = (id, size = 300) => `/api/media/${id}/thumbnail?size=${size}`
export const getFileUrl = (id) => `/api/media/${id}/file`
export const getStreamUrl = (id) => `/api/media/${id}/stream`

export default api
