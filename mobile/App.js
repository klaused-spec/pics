import AsyncStorage from '@react-native-async-storage/async-storage'
import { Audio, ResizeMode, Video } from 'expo-av'
import * as DocumentPicker from 'expo-document-picker'
// SDK 54: a API clássica (documentDirectory, readAsStringAsync, etc.) migrou
// para o submódulo /legacy. Mantemos ela para não reescrever toda a lógica.
import * as FileSystem from 'expo-file-system/legacy'
import { Image as ExpoImage } from 'expo-image'
import * as MediaLibrary from 'expo-media-library'
import { StatusBar } from 'expo-status-bar'
import { Unzip, UnzipInflate } from 'fflate'
import { memo, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  Animated,
  AppState,
  BackHandler,
  Easing,
  FlatList,
  Image,
  Modal,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'
// SDK 54 / RN 0.81 ativou edge-to-edge por padrão no Android: o app desenha por
// baixo das barras do sistema. Usamos o safe-area-context para respeitar os
// insets (topo e, principalmente, a barra de navegação inferior).
import { SafeAreaProvider, SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context'

const SETTINGS_KEY = 'pics_mobile_settings'
const ITEMS_KEY = 'pics_mobile_items'
const ALBUMS_KEY = 'pics_mobile_albums'
const THUMB_DIR = `${FileSystem.documentDirectory}thumbs/`
const FULL_DIR = `${FileSystem.documentDirectory}full/`
// Lista completa da biblioteca em arquivo (AsyncStorage não escala para 100k+ itens).
const ITEMS_FILE = `${FileSystem.documentDirectory}items.json`
const ITEMS_CHUNK_DIR = `${FileSystem.documentDirectory}items_chunks/`
const ITEMS_CHUNK_SIZE = 8000 // itens por arquivo — ~4-6 MB cada, bem abaixo do limite do bridge RN
const DEFAULT_SLIDE_SECONDS = 5
const SCRUB_THUMB = 44
const GALLERY_ALBUM = 'Pics'
const GRID_COLUMNS = 3
const TILE_GAP = 4

function normalizeBaseUrl(value) {
  const trimmed = value.trim()
  const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`
  return withProtocol.replace(/\/$/, '')
}

function apiUrl(baseUrl, path) {
  return `${normalizeBaseUrl(baseUrl)}/api${path}`
}

function networkErrorMessage(error, url) {
  if (error.name === 'AbortError') {
    return `Tempo esgotado tentando conectar em ${url}`
  }
  if (/network request failed/i.test(error.message)) {
    return `Falha de rede tentando conectar em ${url}. Confira se o celular acessa esse endereco e se ele comeca com http:// ou https://.`
  }
  return error.message
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 12000) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(url, { ...options, signal: controller.signal })
  } finally {
    clearTimeout(timeout)
  }
}

function authHeaders(token) {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function formatDuration(seconds) {
  const total = Math.round(Number(seconds) || 0)
  if (total <= 0) return null
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  if (h > 0) return m > 0 ? `${h}h${m}min` : `${h}h`
  if (m > 0) return `${m}min`
  return `${s}s`
}

async function ensureDirectories() {
  await FileSystem.makeDirectoryAsync(THUMB_DIR, { intermediates: true })
  await FileSystem.makeDirectoryAsync(FULL_DIR, { intermediates: true })
  await FileSystem.makeDirectoryAsync(ITEMS_CHUNK_DIR, { intermediates: true })
}

// Concatena vários Uint8Array (pedaços de um mesmo arquivo do zip) em um só.
function concatUint8(chunks) {
  let total = 0
  for (const c of chunks) total += c.length
  const out = new Uint8Array(total)
  let off = 0
  for (const c of chunks) {
    out.set(c, off)
    off += c.length
  }
  return out
}

const B64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

// Converte um Uint8Array em string base64 (para gravar com EncodingType.Base64).
// Implementação própria: React Native não tem btoa confiável para binário.
function fromByteArrayBase64(bytes) {
  let result = ''
  const len = bytes.length
  for (let i = 0; i < len; i += 3) {
    const b0 = bytes[i]
    const b1 = i + 1 < len ? bytes[i + 1] : 0
    const b2 = i + 2 < len ? bytes[i + 2] : 0
    result += B64_CHARS[b0 >> 2]
    result += B64_CHARS[((b0 & 3) << 4) | (b1 >> 4)]
    result += i + 1 < len ? B64_CHARS[((b1 & 15) << 2) | (b2 >> 6)] : '='
    result += i + 2 < len ? B64_CHARS[b2 & 63] : '='
  }
  return result
}

// Índice reverso char->valor para decodificar base64.
const B64_LOOKUP = (() => {
  const t = new Int16Array(256).fill(-1)
  for (let i = 0; i < B64_CHARS.length; i++) t[B64_CHARS.charCodeAt(i)] = i
  return t
})()

// Converte uma string base64 em Uint8Array (inversa de fromByteArrayBase64).
function toByteArrayBase64(b64) {
  // Remove qualquer whitespace/quebra.
  const clean = b64.replace(/[^A-Za-z0-9+/=]/g, '')
  let len = clean.length
  let pad = 0
  if (len && clean[len - 1] === '=') pad++
  if (len > 1 && clean[len - 2] === '=') pad++
  const outLen = ((len * 3) >> 2) - pad
  const out = new Uint8Array(outLen)
  let o = 0
  for (let i = 0; i < len; i += 4) {
    const c0 = B64_LOOKUP[clean.charCodeAt(i)]
    const c1 = B64_LOOKUP[clean.charCodeAt(i + 1)]
    const c2 = B64_LOOKUP[clean.charCodeAt(i + 2)]
    const c3 = B64_LOOKUP[clean.charCodeAt(i + 3)]
    const n = (c0 << 18) | (c1 << 12) | ((c2 & 63) << 6) | (c3 & 63)
    if (o < outLen) out[o++] = (n >> 16) & 0xff
    if (o < outLen) out[o++] = (n >> 8) & 0xff
    if (o < outLen) out[o++] = n & 0xff
  }
  return out
}

async function persistItemCache(nextItems) {
  // Grava em CHUNKS de ITEMS_CHUNK_SIZE itens para não estourar o limite do
  // bridge React Native (~60 MB por string). Com 100k itens o JSON único passa
  // de 50 MB e o writeAsStringAsync falha silenciosamente — daí o "tudo vazio".
  // Cada chunk fica em items_chunks/chunk_N.json (~4-6 MB), bem dentro do limite.
  // Proteção: nunca sobrescreve cache não-vazio com lista vazia.
  if (!nextItems || nextItems.length === 0) {
    const existing = await loadItemCache()
    if (existing.length > 0) return existing.length
    // Cache já está vazio — pode limpar tudo.
  }
  try {
    await FileSystem.makeDirectoryAsync(ITEMS_CHUNK_DIR, { intermediates: true })
    // Remove chunks antigos.
    const dirInfo = await FileSystem.getInfoAsync(ITEMS_CHUNK_DIR)
    if (dirInfo.exists) {
      const existing = await FileSystem.readDirectoryAsync(ITEMS_CHUNK_DIR).catch(() => [])
      await Promise.all(
        existing
          .filter((f) => f.startsWith('chunk_') && f.endsWith('.json'))
          .map((f) => FileSystem.deleteAsync(`${ITEMS_CHUNK_DIR}${f}`, { idempotent: true }))
      )
    }
    // Grava novos chunks em paralelo (cada um pequeno o suficiente para o bridge).
    const writes = []
    for (let i = 0; i * ITEMS_CHUNK_SIZE < nextItems.length; i++) {
      const slice = nextItems.slice(i * ITEMS_CHUNK_SIZE, (i + 1) * ITEMS_CHUNK_SIZE)
      writes.push(
        FileSystem.writeAsStringAsync(`${ITEMS_CHUNK_DIR}chunk_${i}.json`, JSON.stringify(slice))
      )
    }
    await Promise.all(writes)
    // Grava índice (número de chunks) para que loadItemCache saiba quantos ler.
    await FileSystem.writeAsStringAsync(`${ITEMS_CHUNK_DIR}index.json`, JSON.stringify({ chunks: writes.length, total: nextItems.length }))
    // Limpa o arquivo legado de arquivo único, se existir.
    await FileSystem.deleteAsync(ITEMS_FILE, { idempotent: true }).catch(() => {})
    await AsyncStorage.removeItem(ITEMS_KEY).catch(() => {})
  } catch (_) {
    return 0
  }
  return nextItems ? nextItems.length : 0
}

async function loadItemCache() {
  // 1) Tenta chunks (formato novo).
  try {
    const idxPath = `${ITEMS_CHUNK_DIR}index.json`
    if (await fileExists(idxPath)) {
      const idxRaw = await FileSystem.readAsStringAsync(idxPath)
      const idx = JSON.parse(idxRaw)
      if (idx && idx.chunks > 0) {
        const reads = []
        for (let i = 0; i < idx.chunks; i++) {
          reads.push(FileSystem.readAsStringAsync(`${ITEMS_CHUNK_DIR}chunk_${i}.json`))
        }
        const parts = await Promise.all(reads)
        const all = parts.flatMap((p) => JSON.parse(p))
        if (all.length > 0) return all
      }
    }
  } catch (_) {}
  // 2) Fallback: arquivo único legado.
  try {
    if (await fileExists(ITEMS_FILE)) {
      const raw = await FileSystem.readAsStringAsync(ITEMS_FILE)
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length) {
        // Migra para chunks na próxima gravação.
        persistItemCache(parsed).catch(() => {})
        return parsed
      }
    }
  } catch (_) {}
  // 3) Fallback: AsyncStorage legado.
  try {
    const legacy = await AsyncStorage.getItem(ITEMS_KEY)
    if (legacy) {
      const parsed = JSON.parse(legacy)
      if (Array.isArray(parsed) && parsed.length) {
        persistItemCache(parsed).catch(() => {})
        await AsyncStorage.removeItem(ITEMS_KEY).catch(() => {})
        return parsed
      }
    }
  } catch (_) {}
  return []
}

function extensionFromContent(item) {
  if (item.media_type === 'video') return '.mp4'
  const fromName = item.filename?.match(/\.[a-z0-9]+$/i)?.[0]
  if (fromName) return fromName.toLowerCase()
  return '.jpg'
}

function thumbPath(item) {
  return `${THUMB_DIR}${item.id}.jpg`
}

function fullPath(item) {
  const version = item.sha256_hash || item.updated_at || 'current'
  return `${FULL_DIR}${item.id}_${encodeURIComponent(version)}${extensionFromContent(item)}`
}

const MemoTile = memo(function MemoTile({
  item,
  isSelected,
  isOffline,
  selectMode,
  onPress,
  onLongPress,
  onThumbError,
  source,
}) {
  return (
    <Pressable style={styles.tile} onPress={onPress} onLongPress={onLongPress} delayLongPress={250}>
      {item.thumbnail_failed ? (
        <View style={[styles.thumb, styles.thumbMissing]}>
          <Text style={styles.thumbMissingText}>SEM THUMB</Text>
        </View>
      ) : (
        <ExpoImage
          source={source}
          style={styles.thumb}
          contentFit="cover"
          cachePolicy="memory-disk"
          recyclingKey={String(item.id)}
          transition={0}
          onError={onThumbError}
        />
      )}
      {isOffline && <Text style={styles.offlineBadge}>OFFLINE</Text>}
      {item.media_type === 'video' && (
        <View style={styles.videoBadge}>
          <Text style={styles.videoBadgeText}>▶ {formatDuration(item.duration_seconds) || 'Vídeo'}</Text>
        </View>
      )}
      {selectMode && (
        <View style={[styles.selectMark, isSelected && styles.selectMarkActive]}>
          <Text style={styles.selectMarkText}>{isSelected ? '✓' : ''}</Text>
        </View>
      )}
    </Pressable>
  )
})

const MONTH_NAMES = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']

function folderName(folder) {
  if (!folder) return 'Sem pasta'
  const parts = folder.split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] || 'Sem pasta'
}

// Deriva ano/mês do caminho físico da pasta (ex.: .../2026_05/... ou .../2026/05/...),
// para agrupar a pasta no mês onde ela realmente está — igual ao webapp — em vez
// de usar a data individual de cada foto.
function folderMonthKey(folder) {
  if (!folder) return null
  const path = String(folder).replace(/\\/g, '/')
  let match = path.match(/(?:^|\/)(\d{4})_(\d{2})(?:\/|$)/)
  if (!match) match = path.match(/(?:^|\/)(\d{4})\/(\d{2})(?:\/|$)/)
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  if (!year || month < 1 || month > 12) return null
  return { year, month }
}

function dateKey(item) {
  if (item.date_taken) return item.date_taken.slice(0, 10)
  if (item.year && item.month) return `${item.year}-${String(item.month).padStart(2, '0')}`
  return 'sem-data'
}

function dateTitle(key) {
  if (key === 'sem-data') return 'Sem data'
  const parts = key.split('-')
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`
  if (parts.length === 2) return `${parts[1]}/${parts[0]}`
  return key
}

function chunkItems(groupItems, size) {
  const chunks = []
  for (let index = 0; index < groupItems.length; index += size) {
    chunks.push(groupItems.slice(index, index + size))
  }
  return chunks
}

async function fileExists(uri) {
  const info = await FileSystem.getInfoAsync(uri)
  return info.exists
}

async function downloadWithAuth(url, destination, token, onProgress) {
  const download = FileSystem.createDownloadResumable(
    url,
    destination,
    { headers: authHeaders(token) },
    ({ totalBytesWritten, totalBytesExpectedToWrite }) => {
      if (totalBytesExpectedToWrite > 0 && onProgress) {
        onProgress(totalBytesWritten / totalBytesExpectedToWrite)
      }
    },
  )
  const result = await download.downloadAsync()
  if (result.status < 200 || result.status >= 300) {
    await FileSystem.deleteAsync(destination, { idempotent: true })
    const error = new Error(`Download falhou (${result.status})`)
    error.status = result.status
    throw error
  }
  return result.uri
}

// Cache do status de permissão para não perguntar mais de uma vez.
let mediaPermissionGranted = false

async function hasMediaPermission() {
  if (mediaPermissionGranted) return true
  const current = await MediaLibrary.getPermissionsAsync()
  mediaPermissionGranted = !!current.granted
  return mediaPermissionGranted
}

async function ensureMediaPermission() {
  if (await hasMediaPermission()) return true
  const asked = await MediaLibrary.requestPermissionsAsync()
  mediaPermissionGranted = !!asked.granted
  return mediaPermissionGranted
}

// Nome determinístico com o id do item embutido, para o app reconhecer na galeria
// qual mídia já está baixada (ex.: pics_123_IMG_0001.jpg).
function galleryFileName(item) {
  const original = (item.filename || `${item.id}${extensionFromContent(item)}`).replace(/[\\/]/g, '_')
  return `pics_${item.id}_${original}`
}

function parseGalleryId(filename) {
  const match = String(filename || '').match(/^pics_(\d+)_/)
  return match ? Number(match[1]) : null
}

// Prepara um arquivo temporário com o nome-chave antes de mandar para a galeria.
async function stageForGallery(uri, item) {
  const target = `${FileSystem.cacheDirectory}${galleryFileName(item)}`
  try {
    if (await fileExists(target)) {
      await FileSystem.deleteAsync(target, { idempotent: true })
    }
    await FileSystem.copyAsync({ from: uri, to: target })
    return target
  } catch (_) {
    return uri
  }
}

async function getPicsAlbum() {
  try {
    return await MediaLibrary.getAlbumAsync(GALLERY_ALBUM)
  } catch (_) {
    return null
  }
}

// Lê os ids de mídia que já estão na pasta "Pics" da galeria.
async function listGalleryCachedIds() {
  if (!(await hasMediaPermission())) return new Set()
  const album = await getPicsAlbum()
  if (!album) return new Set()
  const ids = new Set()
  let after
  try {
    do {
      const page = await MediaLibrary.getAssetsAsync({
        album,
        first: 200,
        after,
        mediaType: [MediaLibrary.MediaType.photo, MediaLibrary.MediaType.video],
      })
      for (const asset of page.assets) {
        const id = parseGalleryId(asset.filename)
        if (id != null) ids.add(id)
      }
      after = page.hasNextPage ? page.endCursor : null
    } while (after)
  } catch (_) {}
  return ids
}

// Encontra o asset na galeria correspondente a um item (pelo id no nome).
async function findGalleryAsset(item) {
  if (!(await hasMediaPermission())) return null
  const album = await getPicsAlbum()
  if (!album) return null
  const wanted = `pics_${item.id}_`
  let after
  try {
    do {
      const page = await MediaLibrary.getAssetsAsync({
        album,
        first: 200,
        after,
        mediaType: [MediaLibrary.MediaType.photo, MediaLibrary.MediaType.video],
      })
      const found = page.assets.find((asset) => String(asset.filename || '').startsWith(wanted))
      if (found) {
        try {
          const info = await MediaLibrary.getAssetInfoAsync(found)
          return { asset: found, uri: info.localUri || found.uri }
        } catch (_) {
          return { asset: found, uri: found.uri }
        }
      }
      after = page.hasNextPage ? page.endCursor : null
    } while (after)
  } catch (_) {}
  return null
}

// Salva o arquivo baixado na pasta "Pics" da galeria e retorna a uri local do asset.
async function saveItemToGalleryFile(tempUri, item) {
  const granted = await ensureMediaPermission()
  if (!granted) {
    const error = new Error('Permissão para a galeria negada')
    error.code = 'PERMISSION'
    throw error
  }
  const staged = await stageForGallery(tempUri, item)
  const asset = await MediaLibrary.createAssetAsync(staged)
  try {
    const album = await getPicsAlbum()
    if (!album) {
      await MediaLibrary.createAlbumAsync(GALLERY_ALBUM, asset, true)
    } else {
      await MediaLibrary.addAssetsToAlbumAsync([asset], album, true)
    }
  } catch (_) {
    // Se falhar o agrupamento, o asset já está na galeria.
  }
  if (staged !== tempUri) {
    await FileSystem.deleteAsync(staged, { idempotent: true }).catch(() => {})
  }
  let localUri = asset.uri
  try {
    const info = await MediaLibrary.getAssetInfoAsync(asset)
    localUri = info.localUri || asset.uri
  } catch (_) {}
  return { asset, uri: localUri }
}

export default function App() {
  return (
    <SafeAreaProvider>
      <AppInner />
    </SafeAreaProvider>
  )
}

function AppInner() {
  const insets = useSafeAreaInsets()
  const [baseUrl, setBaseUrl] = useState('https://pics.meulavoro.com.br:8443')
  const [email, setEmail] = useState('klaused@gmail.com')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [items, setItems] = useState([])
  // Espelho de `items` sempre atualizado, para evitar closures obsoletas
  // (ex.: sync ao retomar do background usava o `items` inicial vazio e zerava tudo).
  const itemsRef = useRef([])
  const [syncToken, setSyncToken] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [syncStatus, setSyncStatus] = useState('')
  // Download offline opcional (manual) de TODAS as thumbnails para o disco.
  const [offlineThumbs, setOfflineThumbs] = useState(false)
  const [offlineStatus, setOfflineStatus] = useState('')
  const offlineThumbsRef = useRef(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [mediaFilter, setMediaFilter] = useState('all')
  const [offlineOnly, setOfflineOnly] = useState(false)
  const [cachedFullIds, setCachedFullIds] = useState(new Set())
  const [hasPendingSync, setHasPendingSync] = useState(false)
  const [activeTab, setActiveTab] = useState('photos')
  const [selected, setSelected] = useState(null)
  const [fullUri, setFullUri] = useState(null)
  const [fullLoading, setFullLoading] = useState(false)
  const [savingGallery, setSavingGallery] = useState(false)
  const [fullProgress, setFullProgress] = useState(0)
  const [scrubLabel, setScrubLabel] = useState('')
  const [scrubbing, setScrubbing] = useState(false)
  const listRef = useRef(null)
  const scrubTrackRef = useRef({ y: 0, height: 0 })
  const anchorsRef = useRef([])
  // Altura dinâmica de cada linha (tile row e date header). Medida no onLayout
  // da primeira tileRow e usada em getItemLayout para evitar que o FlatList
  // tenha que medir cada item individualmente (principal causa de jank em listas grandes).
  const tileRowHeightRef = useRef(0)
  const dateHeaderHeightRef = useRef(36)
  const scrubbingRef = useRef(false)
  const viewerItemsRef = useRef([])
  const selectedRef = useRef(null)
  // Zoom/pan do viewer
  const viewerScale = useRef(new Animated.Value(1)).current
  const viewerTranslateX = useRef(new Animated.Value(0)).current
  const viewerTranslateY = useRef(new Animated.Value(0)).current
  const viewerZoomRef = useRef({ scale: 1, tx: 0, ty: 0, lastTap: 0 })
  const listMetricsRef = useRef({ offset: 0, contentHeight: 1, viewHeight: 1 })
  const thumbTop = useRef(new Animated.Value(0)).current
  const trackUsableRef = useRef(1)

  // Controle de sync: guarda contexto para retomada manual, nunca automática.
  const syncingRef = useRef(false)
  const syncInterruptedRef = useRef(false)
  const syncCtxRef = useRef({ token: '', baseUrl: '' })

  const [treeExpanded, setTreeExpanded] = useState({})
  const [treeSelected, setTreeSelected] = useState(null)

  const [albums, setAlbums] = useState([])
  const [openAlbumId, setOpenAlbumId] = useState(null)
  // Mídias de cada álbum vindas do backend (mapa albumId -> array de itens).
  // O álbum pode conter mídias que NÃO estão na lista sincronizada `items`
  // (duplicadas/não-organizadas), então buscamos direto do servidor ao abrir.
  const [albumMedia, setAlbumMedia] = useState({})
  const [selectMode, setSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [slideSeconds, setSlideSeconds] = useState(DEFAULT_SLIDE_SECONDS)

  const [newAlbumName, setNewAlbumName] = useState('')
  const [showNewAlbum, setShowNewAlbum] = useState(false)
  const [renameAlbumId, setRenameAlbumId] = useState(null)
  const [renameAlbumName, setRenameAlbumName] = useState('')

  const [slideshow, setSlideshow] = useState(null)
  const [slideIndex, setSlideIndex] = useState(0)
  const [slidePreparing, setSlidePreparing] = useState('')
  const slideOpacity = useRef(new Animated.Value(1)).current
  const slideTimerRef = useRef(null)

  // Mantém o espelho de items sempre atualizado.
  useEffect(() => {
    itemsRef.current = items
  }, [items])

  useEffect(() => {
    Audio.setAudioModeAsync({ playsInSilentModeIOS: true }).catch(() => {})
    boot()
    // Ao voltar ao app, reconcilia a tag OFFLINE com o que está na pasta Pics
    // (caso o usuário tenha apagado fotos por fora). Sync so pode ser manual.
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') {
        refreshCachedFullIds()
      }
    })
    return () => sub.remove()
  }, [])

  // Botão voltar do Android: desfaz a navegação interna em vez de minimizar.
  useEffect(() => {
    const onBack = () => {
      if (showNewAlbum) { setShowNewAlbum(false); return true }
      if (slideshow) { stopSlideshow(); return true }
      if (selected) { setSelected(null); return true }
      if (selectMode) { cancelSelection(); return true }
      if (activeTab === 'tree' && treeSelected) { setTreeSelected(null); return true }
      if (activeTab === 'albums' && openAlbumId) { setOpenAlbumId(null); return true }
      if (activeTab !== 'photos') { setActiveTab('photos'); return true }
      return false
    }
    const sub = BackHandler.addEventListener('hardwareBackPress', onBack)
    return () => sub.remove()
  }, [showNewAlbum, slideshow, selected, selectMode, activeTab, treeSelected, openAlbumId])

  async function boot() {
    await ensureDirectories()
    // Pede permissão da galeria uma única vez no início; assim o salvamento
    // automático dos arquivos offline nunca pergunta foto a foto.
    ensureMediaPermission().catch(() => {})
    await refreshCachedFullIds()
    const [storedSettings, cachedItems, storedAlbums] = await Promise.all([
      AsyncStorage.getItem(SETTINGS_KEY),
      loadItemCache(),
      AsyncStorage.getItem(ALBUMS_KEY),
    ])
    if (cachedItems.length) {
      setItems(cachedItems)
    }
    if (storedAlbums) {
      try { setAlbums(JSON.parse(storedAlbums)) } catch (_) {}
    }
    if (storedSettings) {
      const parsed = JSON.parse(storedSettings)
      setBaseUrl(parsed.baseUrl || baseUrl)
      setEmail(parsed.email || '')
      setToken(parsed.token || '')
      setSyncToken(parsed.syncToken || null)
      if (parsed.slideSeconds) setSlideSeconds(parsed.slideSeconds)
      if (parsed.token) {
        loadAlbums(parsed.token, parsed.baseUrl || baseUrl)
      }
    }
  }

  async function persistSettings(next = {}) {
    const settings = {
      baseUrl,
      email,
      token,
      syncToken,
      slideSeconds,
      ...next,
    }
    await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
  }

  async function cacheAlbums(nextAlbums) {
    await AsyncStorage.setItem(ALBUMS_KEY, JSON.stringify(nextAlbums)).catch(() => {})
  }

  async function loadAlbums(activeToken = token, activeBaseUrl = baseUrl) {
    if (!activeToken) return
    try {
      const url = apiUrl(activeBaseUrl, '/albums/?include_items=true')
      const response = await fetchWithTimeout(url, { headers: authHeaders(activeToken) })
      if (!response.ok) throw new Error(`Álbuns falharam (${response.status})`)
      const data = await response.json()
      const mapped = (Array.isArray(data) ? data : []).map((album) => ({
        id: String(album.id),
        name: album.name,
        itemIds: (album.item_ids || []).map((id) => Number(id)),
      }))
      setAlbums(mapped)
      await cacheAlbums(mapped)
    } catch (_) {
      // Mantém o cache local quando estiver offline
    }
  }

  // Busca as mídias de um álbum direto do backend (que retorna TODAS, inclusive
  // as que não estão na lista sincronizada). Cada item é montado no formato que
  // a grade usa; quando a mídia já existe em `items`, reaproveita a thumbnail
  // local (offline). thumbnail_url do backend vem relativo (/api/...), então
  // aqui viramos absoluto para o expo-image conseguir baixar.
  async function loadAlbumMedia(albumId, activeToken = token, activeBaseUrl = baseUrl) {
    if (!activeToken || !albumId) return
    try {
      const base = normalizeBaseUrl(activeBaseUrl)
      const byId = new Map(items.map((it) => [it.id, it]))
      const collected = []
      let page = 1
      while (true) {
        const url = apiUrl(activeBaseUrl, `/albums/${albumId}/media?page=${page}&per_page=200`)
        const response = await fetchWithTimeout(url, { headers: authHeaders(activeToken) })
        if (!response.ok) throw new Error(`Álbum falhou (${response.status})`)
        const data = await response.json()
        for (const raw of data.items || []) {
          const local = byId.get(raw.id)
          const absoluteThumb = raw.thumbnail_url
            ? (/^https?:\/\//i.test(raw.thumbnail_url) ? raw.thumbnail_url : `${base}${raw.thumbnail_url}`)
            : (local ? local.thumbnail_url : `${base}/api/media/${raw.id}/thumbnail?size=300`)
          collected.push({
            ...raw,
            thumbnail_url: absoluteThumb,
            local_thumbnail_uri: local ? local.local_thumbnail_uri : null,
            thumbnail_failed: local ? local.thumbnail_failed : false,
          })
        }
        if (!data.pages || page >= data.pages) break
        page += 1
      }
      setAlbumMedia((prev) => ({ ...prev, [albumId]: collected }))
    } catch (_) {
      // Offline ou erro: cai no fallback (lista sincronizada) na renderização.
    }
  }

  function createAlbum() {
    setNewAlbumName('')
    setShowNewAlbum(true)
  }

  async function confirmCreateAlbum() {
    const trimmed = newAlbumName.trim() || `Álbum ${albums.length + 1}`
    const mediaIds = selectMode ? Array.from(selectedIds) : []
    setShowNewAlbum(false)
    setNewAlbumName('')
    try {
      const url = apiUrl(baseUrl, '/albums/')
      const response = await fetchWithTimeout(url, {
        method: 'POST',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmed, media_ids: mediaIds }),
      })
      if (!response.ok) throw new Error(`Falha ao criar álbum (${response.status})`)
      if (selectMode) {
        setSelectMode(false)
        setSelectedIds(new Set())
      }
      await loadAlbums()
    } catch (error) {
      Alert.alert('Álbuns', networkErrorMessage(error, apiUrl(baseUrl, '/albums/')))
    }
  }

  async function addSelectedToAlbum(albumId) {
    const ids = Array.from(selectedIds)
    if (!ids.length) return
    try {
      const url = apiUrl(baseUrl, `/albums/${albumId}/media`)
      const response = await fetchWithTimeout(url, {
        method: 'POST',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ media_ids: ids }),
      })
      if (!response.ok) throw new Error(`Falha ao adicionar (${response.status})`)
      setSelectMode(false)
      setSelectedIds(new Set())
      await loadAlbums()
    } catch (error) {
      Alert.alert('Álbuns', networkErrorMessage(error, apiUrl(baseUrl, `/albums/${albumId}/media`)))
    }
  }

  async function removeFromAlbum(albumId, itemId) {
    try {
      const url = apiUrl(baseUrl, `/albums/${albumId}/media`)
      const response = await fetchWithTimeout(url, {
        method: 'DELETE',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ media_ids: [itemId] }),
      })
      if (!response.ok) throw new Error(`Falha ao remover (${response.status})`)
      await loadAlbums()
    } catch (error) {
      Alert.alert('Álbuns', networkErrorMessage(error, apiUrl(baseUrl, `/albums/${albumId}/media`)))
    }
  }

  function startRenameAlbum(album) {
    setRenameAlbumId(album.id)
    setRenameAlbumName(album.name)
  }

  async function confirmRenameAlbum() {
    const albumId = renameAlbumId
    const trimmed = renameAlbumName.trim()
    setRenameAlbumId(null)
    if (!albumId || !trimmed) return
    try {
      const url = apiUrl(baseUrl, `/albums/${albumId}`)
      const response = await fetchWithTimeout(url, {
        method: 'PUT',
        headers: { ...authHeaders(token), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmed }),
      })
      if (!response.ok) throw new Error(`Falha ao renomear (${response.status})`)
      await loadAlbums()
    } catch (error) {
      Alert.alert('Álbuns', networkErrorMessage(error, apiUrl(baseUrl, `/albums/${albumId}`)))
    }
  }

  function deleteAlbum(albumId) {
    Alert.alert('Excluir álbum', 'Remover este álbum para todos? As fotos continuam na biblioteca.', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Excluir', style: 'destructive', onPress: async () => {
        try {
          const url = apiUrl(baseUrl, `/albums/${albumId}`)
          const response = await fetchWithTimeout(url, { method: 'DELETE', headers: authHeaders(token) })
          if (!response.ok && response.status !== 204) throw new Error(`Falha ao excluir (${response.status})`)
          if (openAlbumId === albumId) setOpenAlbumId(null)
          await loadAlbums()
        } catch (error) {
          Alert.alert('Álbuns', networkErrorMessage(error, apiUrl(baseUrl, `/albums/${albumId}`)))
        }
      } },
    ])
  }

  function toggleSelect(id) {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function startSelection(id) {
    setSelectMode(true)
    setSelectedIds(new Set([id]))
  }

  function cancelSelection() {
    setSelectMode(false)
    setSelectedIds(new Set())
  }

  async function refreshCachedFullIds() {
    try {
      // O que está "offline" agora é o que existe na pasta "Pics" da galeria.
      const ids = await listGalleryCachedIds()
      setCachedFullIds(ids)
    } catch (_) {
      setCachedFullIds(new Set())
    }
  }

  function markFullCached(id) {
    setCachedFullIds((currentIds) => {
      const nextIds = new Set(currentIds)
      nextIds.add(id)
      return nextIds
    })
  }

  function unmarkFullCached(id) {
    setCachedFullIds((currentIds) => {
      if (!currentIds.has(id)) return currentIds
      const nextIds = new Set(currentIds)
      nextIds.delete(id)
      return nextIds
    })
  }

  async function login() {
    const loginUrl = apiUrl(baseUrl, '/auth/login')
    try {
      const response = await fetchWithTimeout(loginUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      })
      if (!response.ok) {
        let detail = 'Login recusado'
        try {
          const errorData = await response.json()
          detail = errorData.detail || detail
        } catch (_) {}
        throw new Error(`${detail} (${response.status})`)
      }
      const data = await response.json()
      setToken(data.access_token)
      setPassword('')
      await persistSettings({ token: data.access_token })
      await syncLibrary(data.access_token)
    } catch (error) {
      Alert.alert('Login', networkErrorMessage(error, loginUrl))
    }
  }

  async function logout() {
    setToken('')
    setPassword('')
    setSyncStatus('')
    setActiveTab('photos')
    await persistSettings({ token: '' })
  }

  function confirmLogout() {
    Alert.alert('Sair', 'Deseja sair da conta neste celular? Os arquivos offline permanecem salvos.', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Sair', style: 'destructive', onPress: logout },
    ])
  }

  // Busca uma página do manifesto com algumas tentativas (resiliente a falhas de rede).
  async function fetchManifestPage(url, activeToken, attempts = 3) {
    let lastError
    for (let tryIndex = 0; tryIndex < attempts; tryIndex += 1) {
      // Se o app foi para background antes mesmo de tentar, sinaliza imediatamente.
      if (AppState.currentState !== 'active') {
        const interrupted = new Error('background')
        interrupted.code = 'BACKGROUND'
        throw interrupted
      }
      try {
        const response = await fetchWithTimeout(url, { headers: authHeaders(activeToken) }, 15000)
        if (!response.ok) throw new Error(`Manifesto falhou (${response.status})`)
        // Timeout também na leitura do corpo para não ficar pendurado se o stream travar.
        const bodyTimeout = new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Timeout lendo manifesto')), 15000)
        )
        return await Promise.race([response.json(), bodyTimeout])
      } catch (error) {
        lastError = error
        if (AppState.currentState !== 'active') {
          const interrupted = new Error('background')
          interrupted.code = 'BACKGROUND'
          throw interrupted
        }
        if (tryIndex < attempts - 1) {
          await new Promise((resolve) => setTimeout(resolve, 800 * (tryIndex + 1)))
        }
      }
    }
    throw lastError
  }

  async function syncLibrary(activeToken = token, activeBaseUrl = baseUrl, activeSyncToken = syncToken, seedItems = null) {
    if (!activeToken) return
    if (syncingRef.current) return
    syncingRef.current = true
    syncInterruptedRef.current = false
    syncCtxRef.current = { token: activeToken, baseUrl: activeBaseUrl }
    setSyncing(true)
    try {
      await ensureDirectories()

      // Semeia SEMPRE a partir da lista mais recente disponível, nunca de uma
      // closure obsoleta. Ordem de preferência: seed explícito não-vazio ->
      // espelho itemsRef -> cache em disco. Assim, um sync incremental (com
      // `since`) nunca "perde tudo" ao retomar do background/reabrir o app.
      let baseSeed = Array.isArray(seedItems) && seedItems.length ? seedItems : null
      if (!baseSeed && itemsRef.current && itemsRef.current.length) baseSeed = itemsRef.current
      if (!baseSeed) {
        const fromDisk = await loadItemCache()
        if (Array.isArray(fromDisk) && fromDisk.length) baseSeed = fromDisk
      }
      if (!baseSeed) baseSeed = []

      let page = 1
      const requestedSince = activeSyncToken
      let nextSyncToken = activeSyncToken
      const itemMap = new Map(baseSeed.map((item) => [item.id, item]))

      // Flush incremental: mostra os itens recebidos na UI sem bloquear a JS thread
      // com sort de 100k itens a cada página. Durante o sync, a ordem por data_taken
      // é mantida no Map pelo servidor (que envia em ordem crescente de id, não de data),
      // então o sort final (ao terminar o loop) é o único pesado. Durante o loop só
      // atualizamos a contagem para a UI reagir sem travar.
      let lastFlush = Date.now()
      const FLUSH_INTERVAL_MS = 2000
      // Snapshot rápido para a UI (sem sort — mostra conforme chegam)
      const flushProgress = async () => {
        const snapshot = Array.from(itemMap.values())
        setItems(snapshot)
        lastFlush = Date.now()
        // Yield para a UI conseguir renderizar antes de continuar.
        await new Promise((r) => setTimeout(r, 0))
      }
      const buildSorted = () => Array.from(itemMap.values()).sort((left, right) => {
        return (right.date_taken || '').localeCompare(left.date_taken || '')
      })

      // Paginação por keyset (seek method): em vez de OFFSET (que fica cada vez
      // mais lento — pág 66 tem que percorrer 65k linhas), pedimos ao servidor
      // apenas os itens DEPOIS do último recebido. Cada página é O(per_page),
      // sempre rápida. Cursor = (updated_at, id) do último item da página.
      let afterId = null

      while (true) {
        // Interrupção solicitada externamente (ex.: import de pacote iniciado).
        if (syncInterruptedRef.current) {
          const interrupted = new Error('cancelled')
          interrupted.code = 'BACKGROUND'
          throw interrupted
        }
        const sinceParam = requestedSince ? `&since=${encodeURIComponent(requestedSince)}` : ''
        // Cursor keyset por id apenas (PK). NÃO usar updated_at no cursor: há
        // dezenas de milhares de itens com o mesmo updated_at (importação em
        // lote) e o cursor (updated_at,id) emperrava nesses grupos (~81k/110k).
        const cursorParam = (afterId != null)
          ? `&after_id=${encodeURIComponent(afterId)}`
          : ''
        // per_page=500 (era 1000): respostas menores reduzem a chance do stream
        // HTTP/2 do Caddy abortar ("http2: stream closed") em rede movel, que
        // deixava o fetch pendurado e travava o sync numa pagina. Com keyset,
        // cada pagina e rapida, entao o dobro de paginas nao pesa.
        const manifestUrl = apiUrl(activeBaseUrl, `/media/sync/manifest?page=${page}&per_page=500&size=300${sinceParam}${cursorParam}`)
        const data = await fetchManifestPage(manifestUrl, activeToken)
        // Status discreto SÓ na carga inicial (sem cache prévio). No incremental
        // (poucas páginas) não mostra nada — o app fica com a galeria, não com telas.
        if (baseSeed.length === 0) {
          const totalItems = data.total || 0
          setSyncStatus(`Carregando biblioteca… ${Math.min(itemMap.size, totalItems)}/${totalItems}`)
        }

        for (const item of data.items) {
          const previous = itemMap.get(item.id)
          // Só invalida a thumbnail quando o ARQUIVO muda (sha256), não quando
          // o servidor apenas reprocessa AI/faces (que altera updated_at sem
          // mudar a imagem). Isso evita apagar/rebaixar thumbnails à toa e o
          // efeito de "re-sincroniza tudo" toda vez que o app reabre.
          const prevHash = previous?.sha256_hash
          const thumbChanged = prevHash != null && item.sha256_hash != null && prevHash !== item.sha256_hash
          if (thumbChanged) {
            const localThumb = thumbPath(item)
            await FileSystem.deleteAsync(localThumb, { idempotent: true })
          }
          const localThumbnailUri = !thumbChanged && previous?.local_thumbnail_uri ? previous.local_thumbnail_uri : null
          const thumbnailFailed = !thumbChanged && previous?.thumbnail_failed ? true : false
          itemMap.set(item.id, { ...item, local_thumbnail_uri: localThumbnailUri, thumbnail_failed: thumbnailFailed })
        }

        nextSyncToken = data.sync_token

        // Avança o cursor keyset (por id) a partir do próprio servidor
        // (fallback: id do último item da página).
        const prevAfterId = afterId
        if (data.next_cursor && data.next_cursor.after_id != null) {
          afterId = data.next_cursor.after_id
        } else if (data.items.length) {
          afterId = data.items[data.items.length - 1].id
        }

        // Mostra as fotos que chegaram periodicamente — sem sort, para não bloquear a UI.
        if (Date.now() - lastFlush >= FLUSH_INTERVAL_MS) {
          await flushProgress()
        }

        if (!data.has_more) break
        // Guarda anti-loop: se o cursor não avançou, para (não deveria ocorrer
        // com keyset por id, mas evita travar para sempre numa página).
        if (afterId != null && prevAfterId != null && afterId <= prevAfterId) break
        if (!data.items.length) break
        page += 1
      }

      // Flush definitivo: agora sim ordena tudo por data e persiste em disco.
      const sorted = buildSorted()
      setItems(sorted)
      await persistItemCache(sorted)

      setSyncToken(nextSyncToken)
      await persistSettings({ token: activeToken, syncToken: nextSyncToken })
      setHasPendingSync(false)
      setSyncStatus('')

      // O sync é SÓ a lista (diferença incremental via since/keyset). As
      // thumbnails vêm por expo-image (carrega da URL sob demanda e cacheia em
      // disco ao rolar) OU, para offline total, importando o pacote .zip em
      // Configurações > Biblioteca > "Importar pacote offline".
      loadAlbums(activeToken, activeBaseUrl)
    } catch (error) {
      if (error.code === 'BACKGROUND') {
        syncInterruptedRef.current = true
        setHasPendingSync(true)
        setSyncStatus('Sincronização pausada. Toque em Sincronizar para continuar.')
      } else {
        syncInterruptedRef.current = true
        setHasPendingSync(true)
        setSyncStatus('Sincronização interrompida. Toque em Sincronizar para tentar novamente.')
      }
    } finally {
      syncingRef.current = false
      setSyncing(false)
    }
  }

  // Baixa a thumbnail do item para o disco (thumbs/{id}.jpg) e devolve o URI local.
  // Se o arquivo já existe, reusa. Retorna null em caso de falha.
  async function downloadThumb(item, activeToken = token, activeBaseUrl = baseUrl) {
    const localThumb = thumbPath(item)
    try {
      const info = await FileSystem.getInfoAsync(localThumb)
      if (info.exists && info.size > 0) return localThumb
    } catch (_) {}
    // Tenta primeiro o endpoint "cached": serve direto do disco no servidor, sem
    // tocar o banco (evita o lock do SQLite que serializa os downloads e derruba
    // a velocidade para ~100/min). Como o web já gerou as thumbnails, o cache do
    // servidor está quente e o 404 é raro. Fallback: /thumbnail (regenera).
    const cachedUrl = apiUrl(activeBaseUrl, `/media/${item.id}/thumbnail-cached?size=300`)
    const fallbackUrl = item.thumbnail_url || apiUrl(activeBaseUrl, `/media/${item.id}/thumbnail?size=300`)
    for (const remoteUrl of [cachedUrl, fallbackUrl]) {
      try {
        const result = await FileSystem.downloadAsync(remoteUrl, localThumb, { headers: authHeaders(activeToken) })
        if (result.status >= 200 && result.status < 300) return localThumb
        await FileSystem.deleteAsync(localThumb, { idempotent: true }).catch(() => {})
        // 404 no cached -> tenta o fallback; outros erros também caem no fallback.
      } catch (_) {
        await FileSystem.deleteAsync(localThumb, { idempotent: true }).catch(() => {})
      }
    }
    return null
  }

  // Importa um PACOTE OFFLINE (.zip gerado por backend/build_thumb_pack.py):
  // extrai cada {id}.jpg para THUMB_DIR e marca local_thumbnail_uri nos itens,
  // deixando a galeria funcionar sem rede. Escolhido via document picker
  // (pendrive / Downloads). Rápido: lê o zip do disco e grava direto.
  async function importOfflinePack() {
    if (offlineThumbsRef.current) return
    if (syncingRef.current) {
      // Interrompe o sync ativo para o import não concorrer com ele.
      syncInterruptedRef.current = true
      // Aguarda o sync perceber a interrupção (ele checa AppState a cada página).
      // Como não temos um cancel token, apenas sinalizamos e prosseguimos;
      // o sync vai falhar na próxima iteração e soltar o lock.
      await new Promise((r) => setTimeout(r, 800))
    }
    try {
      const picked = await DocumentPicker.getDocumentAsync({
        type: ['application/zip', 'application/octet-stream', '*/*'],
        copyToCacheDirectory: true,
        multiple: false,
      })
      if (picked.canceled || !picked.assets || !picked.assets.length) return
      const asset = picked.assets[0]

      offlineThumbsRef.current = true
      setOfflineThumbs(true)
      setOfflineStatus('Lendo pacote…')
      await ensureDirectories()

      // Descompacta em STREAMING para não estourar a memória (OutOfMemory):
      // lê o zip do disco em blocos, alimenta o Unzip do fflate, e grava cada
      // thumbnail no disco assim que ele sai — liberando a memória a cada item
      // em vez de manter o zip inteiro + todas as entradas descomprimidas na RAM.
      const savedIds = new Set()
      let done = 0
      let importedItems = null // lista de metadados vinda do items.json, se existir

      // Coleta o conteúdo de cada arquivo (chega em pedaços) e, ao fim do
      // arquivo, grava no disco. Serializa as gravações numa fila para não
      // acumular vários JPGs em memória ao mesmo tempo.
      let writeChain = Promise.resolve()
      let pendingWrites = 0

      const unzipper = new Unzip()
      unzipper.register(UnzipInflate) // suporta tanto ZIP_STORED quanto DEFLATE

      unzipper.onfile = (file) => {
        // items.json: metadados de toda a biblioteca — carrega como cache de itens.
        if (file.name === 'items.json') {
          const chunks = []
          file.ondata = (err, chunk, final) => {
            if (err) return
            if (chunk && chunk.length) chunks.push(chunk)
            if (!final) return
            try {
              const bytes = chunks.length === 1 ? chunks[0] : concatUint8(chunks)
              const text = new TextDecoder().decode(bytes)
              const parsed = JSON.parse(text)
              if (Array.isArray(parsed) && parsed.length) importedItems = parsed
            } catch (_) {}
          }
          file.start()
          return
        }

        const m = /^(\d+)\.jpg$/i.exec(file.name)
        if (!m) {
          // manifest.json ou nome inesperado: descarta sem acumular dados.
          file.ondata = () => {}
          file.start()
          return
        }
        const id = parseInt(m[1], 10)
        const chunks = []
        file.ondata = (err, chunk, final) => {
          if (err) return
          if (chunk && chunk.length) chunks.push(chunk)
          if (!final) return
          // Junta os pedaços deste arquivo e enfileira a gravação no disco.
          const jpgBytes = chunks.length === 1 ? chunks[0] : concatUint8(chunks)
          chunks.length = 0
          pendingWrites++
          writeChain = writeChain.then(async () => {
            try {
              const jpgB64 = fromByteArrayBase64(jpgBytes)
              await FileSystem.writeAsStringAsync(`${THUMB_DIR}${id}.jpg`, jpgB64, {
                encoding: FileSystem.EncodingType.Base64,
              })
              savedIds.add(id)
            } catch (_) {}
            pendingWrites--
            done++
            if (done % 500 === 0) {
              setOfflineStatus(`Importando… ${done}`)
              await new Promise((r) => setTimeout(r, 0)) // deixa a UI respirar
            }
          })
        }
        file.start()
      }

      // Lê o zip do disco em blocos e empurra pro unzipper. Como o Base64 do
      // Expo carrega o arquivo inteiro, lemos por FATIAS (posição/tamanho) para
      // manter o pico de memória baixo mesmo em pacotes grandes.
      // Múltiplo de 3: cada leitura Base64 codifica blocos de 3 bytes -> 4 chars.
      // Se o tamanho não for múltiplo de 3, fatias consecutivas desalinhariam e
      // corromperiam os bytes na junção. 4.194.303 = 3 × 1.398.101 (~4 MB).
      const CHUNK = 4194303
      const info = await FileSystem.getInfoAsync(asset.uri, { size: true })
      const fileSize = info.size || 0
      if (!fileSize) {
        setOfflineStatus('Pacote vazio ou inacessível')
        return
      }
      let pos = 0
      while (pos < fileSize) {
        const length = Math.min(CHUNK, fileSize - pos)
        const b64 = await FileSystem.readAsStringAsync(asset.uri, {
          encoding: FileSystem.EncodingType.Base64,
          position: pos,
          length,
        })
        const chunk = toByteArrayBase64(b64)
        pos += length
        const isLast = pos >= fileSize
        try {
          unzipper.push(chunk, isLast)
        } catch (err) {
          setOfflineStatus(`Pacote inválido: ${err?.message || 'não é um zip válido'}`)
          return
        }
        // Espera as gravações pendentes drenarem antes de ler o próximo bloco,
        // evitando acumular muitos JPGs em memória (backpressure).
        if (pendingWrites > 0) await writeChain
        await new Promise((r) => setTimeout(r, 0))
      }

      // Garante que todas as gravações enfileiradas terminaram.
      await writeChain

      if (!savedIds.size && !importedItems) {
        setOfflineStatus('Pacote sem thumbnails')
        return
      }

      if (importedItems && importedItems.length) {
        // Pacote inclui items.json: reconstrói a galeria completa sem sync.
        // Preenche thumbnail_url com baseUrl atual e marca local_thumbnail_uri
        // para os IDs cujos thumbs foram extraídos agora.
        const base = normalizeBaseUrl(baseUrl)
        const merged = importedItems.map((it) => ({
          ...it,
          thumbnail_url: `${base}/api/media/${it.id}/thumbnail?size=300`,
          file_url: `${base}/api/media/${it.id}/file`,
          stream_url: it.media_type === 'video' ? `${base}/api/media/${it.id}/stream` : null,
          local_thumbnail_uri: savedIds.has(it.id) ? thumbPath(it) : it.local_thumbnail_uri || null,
          thumbnail_failed: false,
        }))
        // Ordena por data decrescente (mesmo critério do sync).
        merged.sort((a, b) => (b.date_taken || '').localeCompare(a.date_taken || ''))
        setItems(merged)
        persistItemCache(merged).catch(() => {})
        // Pacote completo: reseta o syncToken para forçar sync incremental leve
        // na próxima vez (não full sync), e limpa estado de sync interrompido.
        setSyncToken(null)
        setHasPendingSync(false)
        setSyncStatus('')
        syncInterruptedRef.current = false
        persistSettings({ syncToken: null }).catch(() => {})
        setOfflineStatus(`Pacote importado: ${merged.length} itens · ${savedIds.size} thumbnails`)
      } else {
        // Pacote antigo (só thumbs): apenas marca local_thumbnail_uri nos itens já conhecidos.
        setItems((current) => {
          const next = current.map((it) =>
            savedIds.has(it.id) ? { ...it, local_thumbnail_uri: thumbPath(it), thumbnail_failed: false } : it
          )
          persistItemCache(next).catch(() => {})
          return next
        })
        setOfflineStatus(`Pacote importado: ${savedIds.size} thumbnails`)
      }
    } catch (err) {
      setOfflineStatus(`Falha ao importar pacote: ${err?.message || err}`)
    } finally {
      offlineThumbsRef.current = false
      setOfflineThumbs(false)
    }
  }

  function markThumbnailFailed(id) {
    setItems((currentItems) => {
      let changed = false
      const nextItems = currentItems.map((item) => {
        if (item.id !== id || item.thumbnail_failed) return item
        changed = true
        return { ...item, thumbnail_failed: true }
      })
      if (!changed) return currentItems
      persistItemCache(nextItems).catch(() => {})
      return nextItems
    })
  }

  function resetViewerZoom() {
    viewerZoomRef.current.scale = 1
    viewerZoomRef.current.tx = 0
    viewerZoomRef.current.ty = 0
    Animated.parallel([
      Animated.spring(viewerScale, { toValue: 1, useNativeDriver: true }),
      Animated.spring(viewerTranslateX, { toValue: 0, useNativeDriver: true }),
      Animated.spring(viewerTranslateY, { toValue: 0, useNativeDriver: true }),
    ]).start()
  }

  function navigateViewer(direction) {
    const list = viewerItemsRef.current
    const cur = selectedRef.current
    if (!list.length || !cur) return
    const idx = list.findIndex((i) => i.id === cur.id)
    const next = list[idx + direction]
    if (next) { resetViewerZoom(); openItem(next) }
  }

  // Touch handlers diretos (mais confiáveis que PanResponder para pinch no Android)
  const panGestureRef = useRef(null) // {startTx, startTy, startX, startY} para pan

  function handleTouchStart(evt) {
    const touches = evt.nativeEvent.touches
    const z = viewerZoomRef.current
    if (touches.length >= 2) {
      // Início do pinch — registra distância inicial
      const t0 = touches[0]; const t1 = touches[1]
      z.pinchStart = Math.hypot(t0.pageX - t1.pageX, t0.pageY - t1.pageY)
      z.pinchScaleStart = z.scale
      panGestureRef.current = null
    } else if (touches.length === 1) {
      // Duplo tap
      const now = Date.now()
      if (now - z.lastTap < 300) { resetViewerZoom(); z.lastTap = 0 }
      else z.lastTap = now
      // Guarda ponto de início para swipe e pan
      panGestureRef.current = {
        startX: touches[0].pageX,
        startY: touches[0].pageY,
        startTx: z.tx,
        startTy: z.ty,
      }
    }
  }

  function handleTouchMove(evt) {
    const touches = evt.nativeEvent.touches
    const z = viewerZoomRef.current
    if (touches.length >= 2) {
      // Pinch zoom
      const t0 = touches[0]; const t1 = touches[1]
      const dist = Math.hypot(t0.pageX - t1.pageX, t0.pageY - t1.pageY)
      if (!z.pinchStart) { z.pinchStart = dist; z.pinchScaleStart = z.scale; return }
      const newScale = Math.max(1, Math.min(5, z.pinchScaleStart * (dist / z.pinchStart)))
      z.scale = newScale
      viewerScale.setValue(newScale)
    } else if (touches.length === 1 && z.scale > 1.05 && panGestureRef.current) {
      // Pan com zoom ativo — relativo ao ponto de início do gesto
      const t = touches[0]
      const { startX, startY, startTx, startTy } = panGestureRef.current
      const newTx = startTx + (t.pageX - startX)
      const newTy = startTy + (t.pageY - startY)
      z.tx = newTx; z.ty = newTy
      viewerTranslateX.setValue(newTx)
      viewerTranslateY.setValue(newTy)
    }
  }

  function handleTouchEnd(evt) {
    const z = viewerZoomRef.current
    const remaining = evt.nativeEvent.touches.length
    if (remaining >= 2) return
    if (remaining === 1) {
      // Voltou para 1 dedo após pinch — reinicia referência de pan
      z.pinchStart = null
      const t = evt.nativeEvent.touches[0]
      panGestureRef.current = { startX: t.pageX, startY: t.pageY, startTx: z.tx, startTy: z.ty }
      return
    }
    // remaining === 0: todos os dedos levantados
    z.pinchStart = null
    if (z.scale > 1.05) {
      // Snap suave de volta se foi longe demais
      const limit = 150 * (z.scale - 1)
      const clampedTx = Math.max(-limit, Math.min(limit, z.tx))
      const clampedTy = Math.max(-limit, Math.min(limit, z.ty))
      if (clampedTx !== z.tx || clampedTy !== z.ty) {
        z.tx = clampedTx; z.ty = clampedTy
        Animated.parallel([
          Animated.spring(viewerTranslateX, { toValue: clampedTx, useNativeDriver: true, friction: 8 }),
          Animated.spring(viewerTranslateY, { toValue: clampedTy, useNativeDriver: true, friction: 8 }),
        ]).start()
      }
      panGestureRef.current = null
      return
    } else if (panGestureRef.current) {
      // Swipe para navegar (só sem zoom)
      const changed = evt.nativeEvent.changedTouches[0]
      if (changed) {
        const dx = changed.pageX - panGestureRef.current.startX
        const dy = changed.pageY - panGestureRef.current.startY
        if (Math.abs(dx) > 60 && Math.abs(dy) < 80) {
          if (dx < 0) navigateViewer(1)
          else navigateViewer(-1)
        }
      }
    }
    panGestureRef.current = null
  }

  // PanResponder vazio — mantido apenas para compatibilidade com código existente
  const viewerPanResponder = useRef({ panHandlers: {} }).current

  async function openItem(item) {
    setSelected(item)
    selectedRef.current = item
    setFullUri(null)
    setFullProgress(0)
    setFullLoading(true)
    try {
      if (item.media_type === 'video') {
        // Vídeos: sempre HLS on-the-fly (720p, sem baixar o arquivo original).
        const base = normalizeBaseUrl(baseUrl)
        const tokenParam = token ? `?token=${encodeURIComponent(token)}` : ''
        const hlsUrl = `${base}/api/media/${item.id}/hls/playlist.m3u8${tokenParam}`
        setFullUri(hlsUrl)
        setFullLoading(false)
      } else {
        // Imagens: procura na galeria offline primeiro, senão baixa o full.
        const existing = await findGalleryAsset(item)
        if (existing) {
          setFullUri(existing.uri)
          markFullCached(item.id)
        } else {
          unmarkFullCached(item.id)
          const uri = await ensureFullDownloaded(item, setFullProgress)
          setFullUri(uri)
        }
      }
    } catch (error) {
      if (error.code === 'PERMISSION') {
        Alert.alert('Galeria', 'Preciso de permissão de acesso às fotos para baixar e salvar na pasta Pics.')
      } else {
        Alert.alert('Arquivo full', error.message)
      }
      setSelected(null)
      selectedRef.current = null
    } finally {
      setFullLoading(false)
    }
  }

  async function clearOfflineFiles() {
    try {
      const album = await getPicsAlbum()
      if (album) {
        const toDelete = []
        let after
        do {
          const page = await MediaLibrary.getAssetsAsync({
            album,
            first: 200,
            after,
            mediaType: [MediaLibrary.MediaType.photo, MediaLibrary.MediaType.video],
          })
          for (const asset of page.assets) {
            if (parseGalleryId(asset.filename) != null) toDelete.push(asset)
          }
          after = page.hasNextPage ? page.endCursor : null
        } while (after)
        if (toDelete.length) {
          await MediaLibrary.deleteAssetsAsync(toDelete)
        }
      }
      await FileSystem.deleteAsync(THUMB_DIR, { idempotent: true }).catch(() => {})
      await ensureDirectories()
      setCachedFullIds(new Set())
      // Limpa as referências às thumbnails locais que acabaram de ser apagadas,
      // para que o próximo sync as baixe de novo (o download em lote é idempotente).
      setItems((currentItems) => {
        const nextItems = currentItems.map((item) => (
          item.local_thumbnail_uri ? { ...item, local_thumbnail_uri: null } : item
        ))
        persistItemCache(nextItems).catch(() => {})
        return nextItems
      })
      setSyncStatus('Fotos offline removidas da pasta Pics')
    } catch (error) {
      Alert.alert('Limpar offline', error.message)
    }
  }

  function confirmClearOfflineFiles() {
    Alert.alert('Limpar offline', 'Apagar da galeria as fotos baixadas na pasta "Pics"?', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Limpar', style: 'destructive', onPress: clearOfflineFiles },
    ])
  }

  // Baixa o arquivo e grava na pasta "Pics" da galeria; retorna a uri local do asset.
  async function ensureFullDownloaded(item, onProgress) {
    const existing = await findGalleryAsset(item)
    if (existing) {
      markFullCached(item.id)
      return existing.uri
    }
    const temp = `${FileSystem.cacheDirectory}dl_${item.id}${extensionFromContent(item)}`
    // file_url/stream_url podem ser null em itens importados de zip antigo;
    // reconstrói a URL a partir do baseUrl nesse caso.
    const base = normalizeBaseUrl(baseUrl)
    const fileUrl = item.file_url || `${base}/api/media/${item.id}/file`
    const streamUrl = item.stream_url || `${base}/api/media/${item.id}/stream`
    const url = item.media_type === 'video' ? streamUrl : fileUrl
    await downloadWithAuth(url, temp, token, onProgress)
    try {
      const saved = await saveItemToGalleryFile(temp, item)
      markFullCached(item.id)
      return saved.uri
    } catch (err) {
      if (err.code === 'PERMISSION') {
        // Sem permissão de galeria: exibe direto do cache temporário (não salva)
        return temp
      }
      throw err
    }
  }

  async function saveItemToGallery(item) {
    setSavingGallery(true)
    try {
      await ensureFullDownloaded(item)
      Alert.alert('Galeria', `Salvo em "${GALLERY_ALBUM}" na galeria do celular.`)
    } catch (error) {
      if (error.code === 'PERMISSION') {
        Alert.alert('Galeria', 'Preciso de permissão de acesso às fotos para salvar na galeria.')
      } else {
        Alert.alert('Galeria', error.message)
      }
    } finally {
      setSavingGallery(false)
    }
  }

  async function saveSelectedToGallery() {
    const chosen = Array.from(selectedIds).map((id) => items.find((it) => it.id === id)).filter(Boolean)
    if (!chosen.length) return
    setSavingGallery(true)
    let ok = 0
    try {
      const granted = await ensureMediaPermission()
      if (!granted) {
        Alert.alert('Galeria', 'Preciso de permissão de acesso às fotos para salvar na galeria.')
        return
      }
      for (const item of chosen) {
        try {
          await ensureFullDownloaded(item)
          ok += 1
        } catch (_) {}
      }
      Alert.alert('Galeria', `${ok}/${chosen.length} salvos em "${GALLERY_ALBUM}".`)
      setSelectMode(false)
      setSelectedIds(new Set())
    } finally {
      setSavingGallery(false)
    }
  }

  async function startSlideshow(album) {
    const fromServer = albumMedia[album.id]
    const albumItems = (fromServer && fromServer.length)
      ? fromServer
      : album.itemIds.map((id) => items.find((item) => item.id === id)).filter(Boolean)
    if (!albumItems.length) {
      Alert.alert('Slideshow', 'Este álbum está vazio.')
      return
    }
    setSlidePreparing(`Preparando 0/${albumItems.length}`)
    const prepared = []
    try {
      for (let index = 0; index < albumItems.length; index += 1) {
        const item = albumItems[index]
        setSlidePreparing(`Baixando ${index + 1}/${albumItems.length}`)
        const uri = await ensureFullDownloaded(item)
        prepared.push({ ...item, localUri: uri })
      }
    } catch (error) {
      Alert.alert('Slideshow', error.message)
      setSlidePreparing('')
      return
    }
    setSlidePreparing('')
    setSlideIndex(0)
    slideOpacity.setValue(1)
    setSlideshow({ album, items: prepared })
  }

  function stopSlideshow() {
    if (slideTimerRef.current) clearTimeout(slideTimerRef.current)
    slideTimerRef.current = null
    setSlideshow(null)
  }

  function advanceSlide(step = 1) {
    setSlideshow((current) => {
      if (!current) return current
      Animated.timing(slideOpacity, { toValue: 0, duration: 350, easing: Easing.inOut(Easing.ease), useNativeDriver: true }).start(() => {
        setSlideIndex((prev) => {
          const total = current.items.length
          return (prev + step + total) % total
        })
        Animated.timing(slideOpacity, { toValue: 1, duration: 350, easing: Easing.inOut(Easing.ease), useNativeDriver: true }).start()
      })
      return current
    })
  }

  useEffect(() => {
    if (!slideshow) return
    if (slideTimerRef.current) clearTimeout(slideTimerRef.current)
    const currentItem = slideshow.items[slideIndex]
    if (currentItem?.media_type === 'video') return
    slideTimerRef.current = setTimeout(() => advanceSlide(1), Math.max(2, slideSeconds) * 1000)
    return () => {
      if (slideTimerRef.current) clearTimeout(slideTimerRef.current)
    }
  }, [slideshow, slideIndex, slideSeconds])

  // Ao abrir um álbum, busca as mídias dele no backend (inclui itens fora da
  // lista sincronizada). Assim álbuns cuja contagem aparece mas abriam vazios
  // passam a mostrar as fotos.
  useEffect(() => {
    if (openAlbumId) loadAlbumMedia(openAlbumId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openAlbumId])

  const groupedLabel = useMemo(() => {
    if (!items.length) return 'Nenhuma mídia offline ainda'
    const first = items[0]
    return `${items.length} itens offline · mais recente ${first.year || '--'}/${String(first.month || '--').padStart(2, '0')}`
  }, [items])

  const deferredSearchQuery = useDeferredValue(searchQuery)
  const gallery = useMemo(() => {
    const query = deferredSearchQuery.trim().toLowerCase()
    const visibleItems = items.filter((item) => {
      if (mediaFilter !== 'all' && item.media_type !== mediaFilter) return false
      if (offlineOnly && !cachedFullIds.has(item.id)) return false
      if (!query) return true
      const searchable = [
        item.filename,
        item.folder,
        item.media_type,
        item.date_taken,
        item.ai_description,
        item.ai_location,
        item.ai_scene_type,
        Array.isArray(item.ai_objects) ? item.ai_objects.join(' ') : item.ai_objects,
        item.year ? String(item.year) : '',
        item.month ? String(item.month).padStart(2, '0') : '',
      ].filter(Boolean).join(' ').toLowerCase()
      return searchable.includes(query)
    })

    const groupedItems = new Map()
    for (const item of visibleItems) {
      const key = dateKey(item)
      if (!groupedItems.has(key)) groupedItems.set(key, [])
      groupedItems.get(key).push(item)
    }

    const rows = []
    const anchors = []
    for (const [key, groupItems] of groupedItems.entries()) {
      anchors.push({ key, title: dateTitle(key), rowIndex: rows.length })
      rows.push({ type: 'date', key: `date-${key}`, title: dateTitle(key), count: groupItems.length })
      for (const [rowIndex, rowItems] of chunkItems(groupItems, 3).entries()) {
        rows.push({ type: 'media', key: `media-${key}-${rowIndex}`, items: rowItems })
      }
    }

    viewerItemsRef.current = visibleItems
    return { rows, anchors, total: visibleItems.length }
  }, [cachedFullIds, deferredSearchQuery, items, mediaFilter, offlineOnly])

  const treeMonths = useMemo(() => {
    const groups = new Map()
    for (const item of items) {
      // Igual ao webapp: a foto entra na seção do mês pela SUA data (date_taken).
      const year = item.year || 0
      const month = item.month || 0
      const key = `${year}-${month}`
      if (!groups.has(key)) groups.set(key, { key, year, month, count: 0, folders: new Map(), items: [] })
      const node = groups.get(key)
      node.count += 1
      node.items.push(item)
      // Igual ao webapp: a pasta só aparece neste mês se o caminho físico do
      // arquivo pertencer ao diretório deste mesmo mês (ex.: .../2026_05/...).
      const folder = item.folder || ''
      if (folder) {
        const derived = folderMonthKey(folder)
        if (derived && derived.year === year && derived.month === month) {
          if (!node.folders.has(folder)) node.folders.set(folder, [])
          node.folders.get(folder).push(item)
        }
      }
    }
    const list = Array.from(groups.values())
    list.sort((a, b) => (b.year - a.year) || (b.month - a.month))
    for (const node of list) {
      node.folderList = Array.from(node.folders.entries())
        .map(([name, folderItems]) => ({ name, items: folderItems }))
        .sort((a, b) => folderName(a.name).localeCompare(folderName(b.name)))
    }
    return list
  }, [items])

  const treeItems = useMemo(() => {
    if (!treeSelected) return []
    const node = treeMonths.find((m) => m.key === treeSelected.key)
    if (!node) return []
    if (treeSelected.folder == null) return node.items
    return node.folders.get(treeSelected.folder) || []
  }, [treeMonths, treeSelected])

  const treeSelectedTitle = useMemo(() => {
    if (!treeSelected) return ''
    const node = treeMonths.find((m) => m.key === treeSelected.key)
    if (!node) return ''
    const base = `${node.month ? MONTH_NAMES[node.month - 1] : 'Sem mês'} ${node.year || ''}`.trim()
    return treeSelected.folder != null ? `${base} · ${folderName(treeSelected.folder)}` : base
  }, [treeMonths, treeSelected])

  // Source de thumbnail para o expo-image: se há arquivo local (offline), usa
  // o file:// direto (sem headers/cacheKey). Senão, usa a URL remota com token
  // e um cacheKey estável (imune à troca de token) — cacheada em disco.
  function thumbSource(item) {
    if (item.local_thumbnail_uri) return { uri: item.local_thumbnail_uri }
    return { uri: item.thumbnail_url, headers: authHeaders(token), cacheKey: `thumb-${item.id}-300` }
  }

  function renderTile(item) {
    const isSelected = selectedIds.has(item.id)
    const onPress = () => {
      if (selectMode) toggleSelect(item.id)
      else openItem(item)
    }
    const onLongPress = () => {
      if (!selectMode) startSelection(item.id)
    }
    return (
      <MemoTile
        key={item.id}
        item={item}
        isSelected={isSelected}
        isOffline={cachedFullIds.has(item.id)}
        selectMode={selectMode}
        onPress={onPress}
        onLongPress={onLongPress}
        onThumbError={() => markThumbnailFailed(item.id)}
        source={thumbSource(item)}
      />
    )
  }

  anchorsRef.current = gallery.anchors

  function ratioLabel(ratio) {
    const anchors = anchorsRef.current
    if (!anchors.length) return ''
    const index = Math.min(anchors.length - 1, Math.max(0, Math.round(ratio * (anchors.length - 1))))
    return anchors[index]?.title || ''
  }

  function handleListScroll(event) {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent
    listMetricsRef.current = {
      offset: contentOffset.y,
      contentHeight: contentSize.height,
      viewHeight: layoutMeasurement.height,
    }
    if (scrubbingRef.current) return
    const scrollable = Math.max(1, contentSize.height - layoutMeasurement.height)
    const ratio = Math.max(0, Math.min(1, contentOffset.y / scrollable))
    thumbTop.setValue(ratio * trackUsableRef.current)
  }

  function scrubToPageY(pageY) {
    const { y, height } = scrubTrackRef.current
    if (!height) return
    const usable = trackUsableRef.current
    const local = Math.max(0, Math.min(usable, pageY - y - SCRUB_THUMB / 2))
    const ratio = usable > 0 ? local / usable : 0
    thumbTop.setValue(local)
    setScrubLabel(ratioLabel(ratio))
    const { contentHeight, viewHeight } = listMetricsRef.current
    const scrollable = Math.max(1, contentHeight - viewHeight)
    listRef.current?.scrollToOffset({ offset: ratio * scrollable, animated: false })
  }

  const scrubViewRef = useRef(null)

  function measureTrack() {
    scrubViewRef.current?.measureInWindow((x, y, width, height) => {
      scrubTrackRef.current = { y, height }
      trackUsableRef.current = Math.max(1, height - SCRUB_THUMB)
    })
  }

  const scrubResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderTerminationRequest: () => false,
      onPanResponderGrant: (evt) => {
        measureTrack()
        scrubbingRef.current = true
        setScrubbing(true)
        scrubToPageY(evt.nativeEvent.pageY)
      },
      onPanResponderMove: (evt) => {
        scrubToPageY(evt.nativeEvent.pageY)
      },
      onPanResponderRelease: () => {
        scrubbingRef.current = false
        setScrubbing(false)
      },
      onPanResponderTerminate: () => {
        scrubbingRef.current = false
        setScrubbing(false)
      },
    }),
  ).current

  const galleryList = (
    <View style={styles.tabContent}>
    <FlatList
      ref={listRef}
      data={gallery.rows}
      keyExtractor={(row) => row.key}
      contentContainerStyle={styles.grid}
      keyboardShouldPersistTaps="handled"
      onScroll={handleListScroll}
      scrollEventThrottle={32}
      windowSize={5}
      maxToRenderPerBatch={8}
      initialNumToRender={12}
      removeClippedSubviews
      getItemLayout={(_, index) => {
        const tileH = tileRowHeightRef.current
        const dateH = dateHeaderHeightRef.current
        // Se ainda não mediu, usa uma estimativa razoável
        const fallbackTile = tileH || 120
        const fallbackDate = dateH || 36
        let offset = 0
        for (let i = 0; i < index; i++) {
          const row = gallery.rows[i]
          offset += row && row.type === 'date' ? fallbackDate : fallbackTile
        }
        const row = gallery.rows[index]
        const length = row && row.type === 'date' ? fallbackDate : fallbackTile
        return { length, offset, index }
      }}
      onScrollToIndexFailed={(info) => {
        listRef.current?.scrollToOffset({ offset: info.averageItemLength * info.index, animated: false })
      }}
      ListEmptyComponent={(
        <View style={styles.emptyState}>
          <Text style={styles.emptyEmoji}>🖼️</Text>
          <Text style={styles.emptyTitle}>Nada por aqui ainda</Text>
          <Text style={styles.emptyText}>{syncing ? 'Sincronizando sua biblioteca...' : 'Toque em Sincronizar em Configurações para carregar suas mídias.'}</Text>
        </View>
      )}
      renderItem={({ item }) => item.type === 'date' ? (
        <View
          style={styles.dateHeader}
          onLayout={({ nativeEvent }) => {
            if (!dateHeaderHeightRef.current) dateHeaderHeightRef.current = nativeEvent.layout.height
          }}
        >
          <Text style={styles.dateTitle}>{item.title}</Text>
          <Text style={styles.dateCount}>{item.count} itens</Text>
        </View>
      ) : (
        <View
          style={styles.tileRow}
          onLayout={({ nativeEvent }) => {
            if (!tileRowHeightRef.current) tileRowHeightRef.current = nativeEvent.layout.height
          }}
        >
          {item.items.map(renderTile)}
          {Array.from({ length: 3 - item.items.length }).map((_, index) => <View key={`empty-${index}`} style={styles.tile} />)}
        </View>
      )}
    />
    {gallery.anchors.length > 1 && (
      <View
        ref={scrubViewRef}
        style={styles.scrubber}
        onLayout={measureTrack}
        {...scrubResponder.panHandlers}
      >
        <View style={styles.scrubberTrack} pointerEvents="none" />
        <Animated.View style={[styles.scrubberThumb, { transform: [{ translateY: thumbTop }] }]} pointerEvents="none">
          <Text style={styles.scrubberThumbText}>⋮</Text>
        </Animated.View>
      </View>
    )}
    {scrubbing && !!scrubLabel && (
      <View style={styles.scrubOverlay} pointerEvents="none">
        <View style={styles.scrubOverlayCard}>
          <Text style={styles.scrubOverlayText}>{scrubLabel}</Text>
        </View>
      </View>
    )}
    </View>
  )

  if (!token) {
    return (
      <SafeAreaView style={styles.loginScreen}>
        <StatusBar style="light" />
        <View style={styles.loginBrand}>
          <View style={styles.loginLogo}>
            <Text style={styles.loginLogoText}>P</Text>
          </View>
          <Text style={styles.loginTitle}>PICS</Text>
          <Text style={styles.loginSubtitle}>Sua biblioteca de fotos e vídeos</Text>
        </View>
        <View style={styles.loginCard}>
          <Text style={styles.inputLabel}>Servidor</Text>
          <TextInput style={styles.input} value={baseUrl} onChangeText={setBaseUrl} placeholder="http://IP-do-servidor:8000" placeholderTextColor="#9aa4b2" selectionColor="#2563eb" cursorColor="#2563eb" autoCapitalize="none" />
          <Text style={styles.inputLabel}>E-mail</Text>
          <TextInput style={styles.input} value={email} onChangeText={setEmail} placeholder="voce@email.com" placeholderTextColor="#9aa4b2" selectionColor="#2563eb" cursorColor="#2563eb" autoCapitalize="none" keyboardType="email-address" />
          <Text style={styles.inputLabel}>Senha</Text>
          <TextInput style={styles.input} value={password} onChangeText={setPassword} placeholder="••••••••" placeholderTextColor="#9aa4b2" selectionColor="#2563eb" cursorColor="#2563eb" secureTextEntry textContentType="password" autoComplete="password" autoCorrect={false} />
          <Pressable style={styles.primaryButton} onPress={login}>
            <Text style={styles.primaryButtonText}>Entrar</Text>
          </Pressable>
          {!!syncStatus && <Text style={styles.status}>{syncStatus}</Text>}
          {!!hasPendingSync && !syncing && <Text style={styles.status}>Há uma sincronização pendente e ela não será retomada automaticamente.</Text>}
        </View>
      </SafeAreaView>
    )
  }

  const openAlbum = albums.find((album) => album.id === openAlbumId) || null

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style="dark" />

      {selectMode && (
        <View style={styles.selectionBar}>
          <Pressable style={styles.selectionCancel} onPress={cancelSelection}>
            <Text style={styles.selectionCancelText}>✕</Text>
          </Pressable>
          <Text style={styles.selectionText}>{selectedIds.size} selecionada(s)</Text>
          <Pressable
            style={styles.selectionNew}
            onPress={() => {
              if (!selectedIds.size) return
              saveSelectedToGallery()
            }}
            disabled={savingGallery}
          >
            {savingGallery ? <ActivityIndicator color="#93c5fd" /> : <Text style={styles.selectionNewText}>⬇ Galeria</Text>}
          </Pressable>
          <Pressable
            style={styles.selectionNew}
            onPress={() => {
              if (!selectedIds.size) return
              createAlbum()
            }}
          >
            <Text style={styles.selectionNewText}>＋ Novo</Text>
          </Pressable>
          <Pressable
            style={styles.selectionAction}
            onPress={() => {
              if (!selectedIds.size) return
              const buttons = [
                { text: '＋ Criar novo álbum', onPress: () => createAlbum() },
                ...albums.map((album) => ({ text: album.name, onPress: () => addSelectedToAlbum(album.id) })),
                { text: 'Cancelar', style: 'cancel' },
              ]
              Alert.alert('Adicionar ao álbum', 'Escolha um álbum ou crie um novo', buttons)
            }}
          >
            <Text style={styles.selectionActionText}>Adicionar</Text>
          </Pressable>
        </View>
      )}

      {activeTab === 'photos' && (
        <View style={styles.tabContent}>
          <View style={styles.topBar}>
            <View>
              <Text style={styles.topTitle}>Fotos</Text>
              <Text style={styles.topSubtitle}>{groupedLabel}</Text>
            </View>
            <Pressable style={styles.iconButton} onPress={() => syncLibrary()} disabled={syncing}>
              {syncing ? <ActivityIndicator color="#2563eb" /> : <Text style={styles.iconButtonText}>↻</Text>}
            </Pressable>
          </View>
          <View style={styles.filterRow}>
            {[
              ['all', 'Tudo'],
              ['image', 'Fotos'],
              ['video', 'Vídeos'],
            ].map(([value, label]) => (
              <Pressable key={value} style={[styles.chip, mediaFilter === value && styles.chipActive]} onPress={() => setMediaFilter(value)}>
                <Text style={[styles.chipText, mediaFilter === value && styles.chipTextActive]}>{label}</Text>
              </Pressable>
            ))}
            <Pressable style={[styles.chip, offlineOnly && styles.chipActive]} onPress={() => setOfflineOnly((value) => !value)}>
              <Text style={[styles.chipText, offlineOnly && styles.chipTextActive]}>Offline</Text>
            </Pressable>
          </View>
          {galleryList}
        </View>
      )}

      {activeTab === 'search' && (
        <View style={styles.tabContent}>
          <View style={styles.topBar}>
            <Text style={styles.topTitle}>Buscar</Text>
          </View>
          <View style={styles.searchWrap}>
            <Text style={styles.searchIcon}>🔍</Text>
            <TextInput style={styles.searchInput} value={searchQuery} onChangeText={setSearchQuery} placeholder="Nome, IA, pasta ou data" placeholderTextColor="#9aa4b2" selectionColor="#2563eb" cursorColor="#2563eb" autoCapitalize="none" />
            {!!searchQuery && (
              <Pressable onPress={() => setSearchQuery('')} style={styles.clearSearch}>
                <Text style={styles.clearSearchText}>✕</Text>
              </Pressable>
            )}
          </View>
          <View style={styles.filterRow}>
            {[
              ['all', 'Tudo'],
              ['image', 'Fotos'],
              ['video', 'Vídeos'],
            ].map(([value, label]) => (
              <Pressable key={value} style={[styles.chip, mediaFilter === value && styles.chipActive]} onPress={() => setMediaFilter(value)}>
                <Text style={[styles.chipText, mediaFilter === value && styles.chipTextActive]}>{label}</Text>
              </Pressable>
            ))}
            <Pressable style={[styles.chip, offlineOnly && styles.chipActive]} onPress={() => setOfflineOnly((value) => !value)}>
              <Text style={[styles.chipText, offlineOnly && styles.chipTextActive]}>Offline</Text>
            </Pressable>
            <Text style={styles.resultCount}>{gallery.total} itens</Text>
          </View>
          {galleryList}
        </View>
      )}

      {activeTab === 'albums' && !openAlbum && (
        <View style={styles.tabContent}>
          <View style={styles.topBar}>
            <Text style={styles.topTitle}>Álbuns</Text>
          </View>
          <Pressable style={styles.newAlbumButton} onPress={createAlbum}>
            <Text style={styles.newAlbumButtonText}>＋ Novo álbum</Text>
          </Pressable>
          <FlatList
            data={albums}
            keyExtractor={(album) => album.id}
            contentContainerStyle={{ paddingBottom: 24 }}
            ListEmptyComponent={(
              <View style={styles.emptyState}>
                <Text style={styles.emptyEmoji}>📁</Text>
                <Text style={styles.emptyTitle}>Nenhum álbum ainda</Text>
                <Text style={styles.emptyText}>Segure uma foto na aba Fotos para adicionar a um álbum.</Text>
              </View>
            )}
            renderItem={({ item: album }) => {
              const cover = album.itemIds.map((id) => items.find((it) => it.id === id)).find(Boolean)
              const openAlbumMenu = () => {
                Alert.alert(album.name, 'O que deseja fazer?', [
                  { text: 'Renomear', onPress: () => startRenameAlbum(album) },
                  { text: 'Excluir', style: 'destructive', onPress: () => deleteAlbum(album.id) },
                  { text: 'Cancelar', style: 'cancel' },
                ])
              }
              return (
                <Pressable style={styles.albumRow} onPress={() => setOpenAlbumId(album.id)} onLongPress={openAlbumMenu} delayLongPress={250}>
                  <View style={styles.albumCover}>
                    {cover ? (
                      <ExpoImage source={thumbSource(cover)} style={{ width: '100%', height: '100%', borderRadius: 10 }} contentFit="cover" cachePolicy="memory-disk" recyclingKey={String(cover.id)} />
                    ) : (
                      <Text style={styles.albumCoverText}>📁</Text>
                    )}
                  </View>
                  <View style={styles.albumInfo}>
                    <Text style={styles.albumName} numberOfLines={1}>{album.name}</Text>
                    <Text style={styles.albumCount}>{album.itemIds.length} itens</Text>
                  </View>
                  <Pressable style={styles.albumEdit} onPress={() => startRenameAlbum(album)} hitSlop={8}>
                    <Text style={styles.albumEditText}>✏️</Text>
                  </Pressable>
                  <Pressable style={styles.albumPlay} onPress={() => startSlideshow(album)}>
                    <Text style={styles.albumPlayText}>▶</Text>
                  </Pressable>
                </Pressable>
              )
            }}
          />
        </View>
      )}

      {activeTab === 'albums' && openAlbum && (
        <View style={styles.tabContent}>
          <View style={styles.albumHeaderBar}>
            <Pressable style={styles.backButton} onPress={() => setOpenAlbumId(null)}>
              <Text style={styles.backButtonText}>← Álbuns</Text>
            </Pressable>
            <Text style={[styles.topTitle, { flex: 1, fontSize: 22 }]} numberOfLines={1}>{openAlbum.name}</Text>
            <Pressable style={styles.albumPlay} onPress={() => startSlideshow(openAlbum)}>
              <Text style={styles.albumPlayText}>▶</Text>
            </Pressable>
          </View>
          <FlatList
            data={chunkItems(
              (albumMedia[openAlbum.id] && albumMedia[openAlbum.id].length)
                ? albumMedia[openAlbum.id]
                : openAlbum.itemIds.map((id) => items.find((it) => it.id === id)).filter(Boolean),
              3,
            )}
            keyExtractor={(_, index) => `album-row-${index}`}
            contentContainerStyle={styles.grid}
            ListEmptyComponent={(
              <View style={styles.emptyState}>
                <Text style={styles.emptyEmoji}>🖼️</Text>
                <Text style={styles.emptyTitle}>Álbum vazio</Text>
                <Text style={styles.emptyText}>Segure fotos na aba Fotos e adicione a este álbum.</Text>
              </View>
            )}
            renderItem={({ item: rowItems }) => (
              <View style={styles.tileRow}>
                {rowItems.map((item) => (
                  <Pressable key={item.id} style={styles.tile} onPress={() => openItem(item)} onLongPress={() => {
                    Alert.alert('Remover do álbum', item.filename, [
                      { text: 'Cancelar', style: 'cancel' },
                      { text: 'Remover', style: 'destructive', onPress: () => removeFromAlbum(openAlbum.id, item.id) },
                    ])
                  }} delayLongPress={250}>
                    {item.thumbnail_failed ? (
                      <View style={[styles.thumb, styles.thumbMissing]}><Text style={styles.thumbMissingText}>SEM THUMB</Text></View>
                    ) : (
                      <ExpoImage source={thumbSource(item)} style={styles.thumb} contentFit="cover" cachePolicy="memory-disk" recyclingKey={String(item.id)} />
                    )}
                    {item.media_type === 'video' && (
                      <View style={styles.videoBadge}>
                        <Text style={styles.videoBadgeText}>▶ {formatDuration(item.duration_seconds) || 'Vídeo'}</Text>
                      </View>
                    )}
                  </Pressable>
                ))}
                {Array.from({ length: 3 - rowItems.length }).map((_, index) => <View key={`empty-${index}`} style={styles.tile} />)}
              </View>
            )}
          />
        </View>
      )}

      {activeTab === 'tree' && !treeSelected && (
        <View style={styles.tabContent}>
          <View style={styles.topBar}>
            <Text style={styles.topTitle}>Pastas</Text>
          </View>
          <FlatList
            data={treeMonths}
            keyExtractor={(node) => node.key}
            contentContainerStyle={{ paddingBottom: 24, paddingHorizontal: 12 }}
            ListEmptyComponent={<View style={styles.emptyState}><Text style={styles.emptyEmoji}>📂</Text><Text style={styles.emptyTitle}>Sem dados</Text><Text style={styles.emptyText}>Sincronize a biblioteca primeiro.</Text></View>}
            renderItem={({ item: node }) => {
              const expanded = !!treeExpanded[node.key]
              const hasFolders = node.folderList.length > 0
              return (
                <View>
                  <Pressable
                    style={styles.treeRow}
                    onPress={() => {
                      if (hasFolders) setTreeExpanded((prev) => ({ ...prev, [node.key]: !prev[node.key] }))
                      else setTreeSelected({ key: node.key, folder: null })
                    }}
                  >
                    <Text style={styles.treeChevron}>{hasFolders ? (expanded ? '▾' : '▸') : '·'}</Text>
                    <Text style={styles.treeIcon}>🗓️</Text>
                    <Text style={styles.treeLabel} numberOfLines={1}>{node.month ? MONTH_NAMES[node.month - 1] : 'Sem mês'} {node.year || ''}</Text>
                    <Text style={styles.treeCount}>{node.count}</Text>
                    <Pressable hitSlop={8} style={styles.treeOpen} onPress={() => setTreeSelected({ key: node.key, folder: null })}>
                      <Text style={styles.treeOpenText}>Ver</Text>
                    </Pressable>
                  </Pressable>
                  {expanded && node.folderList.map((sub) => (
                    <Pressable key={sub.name} style={styles.treeSubRow} onPress={() => setTreeSelected({ key: node.key, folder: sub.name })}>
                      <Text style={styles.treeBranch}>└</Text>
                      <Text style={styles.treeIcon}>📁</Text>
                      <Text style={styles.treeSubLabel} numberOfLines={1}>{folderName(sub.name)}</Text>
                      <Text style={styles.treeCount}>{sub.items.length}</Text>
                    </Pressable>
                  ))}
                </View>
              )
            }}
          />
        </View>
      )}

      {activeTab === 'tree' && treeSelected && (
        <View style={styles.tabContent}>
          <View style={styles.albumHeaderBar}>
            <Pressable style={styles.backButton} onPress={() => setTreeSelected(null)}><Text style={styles.backButtonText}>← Pastas</Text></Pressable>
            <Text style={[styles.topTitle, { flex: 1, fontSize: 18 }]} numberOfLines={1}>{treeSelectedTitle}</Text>
          </View>
          <FlatList
            data={chunkItems(treeItems, 3)}
            keyExtractor={(_, index) => `tree-row-${index}`}
            contentContainerStyle={styles.grid}
            ListEmptyComponent={<View style={styles.emptyState}><Text style={styles.emptyEmoji}>🖼️</Text><Text style={styles.emptyTitle}>Vazio</Text></View>}
            renderItem={({ item: rowItems }) => (
              <View style={styles.tileRow}>
                {rowItems.map(renderTile)}
                {Array.from({ length: 3 - rowItems.length }).map((_, index) => <View key={`empty-${index}`} style={styles.tile} />)}
              </View>
            )}
          />
        </View>
      )}

      {activeTab === 'settings' && (
        <FlatList
          data={[1]}
          keyExtractor={() => 'settings'}
          contentContainerStyle={styles.settingsScroll}
          renderItem={() => (
            <View>
              <View style={styles.topBar}>
                <Text style={styles.topTitle}>Configurações</Text>
              </View>

              <View style={styles.accountCard}>
                <View style={styles.avatar}>
                  <Text style={styles.avatarText}>{(email || 'P').slice(0, 1).toUpperCase()}</Text>
                </View>
                <View style={styles.accountInfo}>
                  <Text style={styles.accountName} numberOfLines={1}>{email || 'Conta PICS'}</Text>
                  <Text style={styles.accountServer} numberOfLines={1}>{normalizeBaseUrl(baseUrl)}</Text>
                </View>
              </View>

              <Text style={styles.sectionLabel}>Servidor</Text>
              <View style={styles.settingsGroup}>
                <TextInput style={styles.input} value={baseUrl} onChangeText={setBaseUrl} placeholder="http://IP-do-servidor:8000" placeholderTextColor="#9aa4b2" selectionColor="#2563eb" cursorColor="#2563eb" autoCapitalize="none" />
                <Pressable style={styles.rowButton} onPress={() => persistSettings()}>
                  <Text style={styles.rowButtonText}>Salvar servidor</Text>
                </Pressable>
              </View>

              <Text style={styles.sectionLabel}>Biblioteca</Text>
              <View style={styles.settingsGroup}>
                <Pressable style={styles.rowItem} onPress={() => syncLibrary()} disabled={syncing}>
                  <Text style={styles.rowItemText}>{syncing ? 'Sincronizando...' : 'Sincronizar biblioteca'}</Text>
                  <Text style={styles.rowItemHint}>↻</Text>
                </Pressable>
                <View style={styles.rowDivider} />
                <Pressable style={styles.rowItem} onPress={importOfflinePack} disabled={offlineThumbs}>
                  <Text style={styles.rowItemText}>{offlineThumbs ? 'Importando pacote…' : 'Importar pacote offline'}</Text>
                  <Text style={styles.rowItemHint}>📦</Text>
                </Pressable>
                <View style={styles.rowDivider} />
                <Pressable style={styles.rowItem} onPress={confirmClearOfflineFiles}>
                  <Text style={[styles.rowItemText, styles.rowItemDanger]}>Limpar arquivos offline</Text>
                  <Text style={styles.rowItemHint}>🗑️</Text>
                </Pressable>
              </View>
              {!!offlineStatus && <Text style={styles.status}>{offlineStatus}</Text>}
              {!!syncStatus && <Text style={styles.status}>{syncStatus}</Text>}

              <Text style={styles.sectionLabel}>Slideshow</Text>
              <View style={styles.settingsGroup}>
                <View style={styles.rowItem}>
                  <Text style={styles.rowItemText}>Tempo por foto</Text>
                  <View style={styles.stepperRow}>
                    <Pressable style={styles.stepperButton} onPress={() => { const next = Math.max(2, slideSeconds - 1); setSlideSeconds(next); persistSettings({ slideSeconds: next }) }}>
                      <Text style={styles.stepperButtonText}>−</Text>
                    </Pressable>
                    <Text style={styles.stepperValue}>{slideSeconds}s</Text>
                    <Pressable style={styles.stepperButton} onPress={() => { const next = Math.min(60, slideSeconds + 1); setSlideSeconds(next); persistSettings({ slideSeconds: next }) }}>
                      <Text style={styles.stepperButtonText}>＋</Text>
                    </Pressable>
                  </View>
                </View>
              </View>

              <Text style={styles.sectionLabel}>Conta</Text>
              <View style={styles.settingsGroup}>
                <Pressable style={styles.rowItem} onPress={confirmLogout}>
                  <Text style={[styles.rowItemText, styles.rowItemDanger]}>Sair da conta</Text>
                  <Text style={styles.rowItemHint}>⎋</Text>
                </Pressable>
              </View>

              <Text style={styles.versionText}>PICS Mobile v0.4.4</Text>
            </View>
          )}
        />
      )}

      <View style={[styles.tabBar, { height: 62 + insets.bottom, paddingBottom: insets.bottom }]}>
        {[
          ['photos', 'Fotos', '🖼️'],
          ['search', 'Buscar', '🔍'],
          ['tree', 'Pastas', '🗂️'],
          ['albums', 'Álbuns', '📁'],
          ['settings', 'Config', '⚙️'],
        ].map(([value, label, icon]) => (
          <Pressable key={value} style={styles.tabButton} onPress={() => { setActiveTab(value); if (value !== 'albums') setOpenAlbumId(null); if (value !== 'tree') setTreeSelected(null) }}>
            <Text style={[styles.tabIcon, activeTab === value && styles.tabIconActive]}>{icon}</Text>
            <Text style={[styles.tabLabel, activeTab === value && styles.tabLabelActive]}>{label}</Text>
          </Pressable>
        ))}
      </View>

      <Modal visible={!!selected} animationType="slide" onRequestClose={() => setSelected(null)}>
        <SafeAreaView style={styles.viewer}>
          <View style={styles.viewerHeader}>
            <Pressable onPress={() => setSelected(null)} style={styles.closeButton}>
              <Text style={styles.closeButtonText}>Fechar</Text>
            </Pressable>
            <Text style={styles.viewerTitle} numberOfLines={1}>{selected?.filename}</Text>
            <Pressable onPress={() => selected && saveItemToGallery(selected)} style={styles.saveButton} disabled={savingGallery || fullLoading}>
              {savingGallery ? <ActivityIndicator color="#ffffff" /> : <Text style={styles.saveButtonText}>⬇ Salvar</Text>}
            </Pressable>
          </View>
          {fullLoading && (
            <View style={styles.loadingFull}>
              <ActivityIndicator size="large" color="#ffffff" />
              <Text style={styles.viewerStatus}>Baixando arquivo full {Math.round(fullProgress * 100)}%</Text>
            </View>
          )}
          {!fullLoading && fullUri && selected?.media_type === 'image' && (
            <View
              style={styles.fullImage}
              onTouchStart={handleTouchStart}
              onTouchMove={handleTouchMove}
              onTouchEnd={handleTouchEnd}
            >
              <Animated.Image
                source={{ uri: fullUri }}
                style={[styles.fullImage, { transform: [{ scale: viewerScale }, { translateX: viewerTranslateX }, { translateY: viewerTranslateY }] }]}
                resizeMode="contain"
              />
            </View>
          )}
          {!fullLoading && fullUri && selected?.media_type === 'video' && (
            <Video source={{ uri: fullUri }} style={styles.fullImage} useNativeControls resizeMode={ResizeMode.CONTAIN} />
          )}
        </SafeAreaView>
      </Modal>

      <Modal visible={showNewAlbum} animationType="fade" transparent onRequestClose={() => setShowNewAlbum(false)}>
        <View style={styles.dialogBackdrop}>
          <View style={styles.dialogCard}>
            <Text style={styles.dialogTitle}>Novo álbum</Text>
            <TextInput style={styles.input} value={newAlbumName} onChangeText={setNewAlbumName} placeholder="Nome do álbum" placeholderTextColor="#9aa4b2" selectionColor="#2563eb" cursorColor="#2563eb" autoFocus />
            <View style={styles.dialogActions}>
              <Pressable style={styles.dialogCancel} onPress={() => setShowNewAlbum(false)}>
                <Text style={styles.dialogCancelText}>Cancelar</Text>
              </Pressable>
              <Pressable style={styles.dialogConfirm} onPress={confirmCreateAlbum}>
                <Text style={styles.dialogConfirmText}>Criar</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>

      <Modal visible={renameAlbumId !== null} animationType="fade" transparent onRequestClose={() => setRenameAlbumId(null)}>
        <View style={styles.dialogBackdrop}>
          <View style={styles.dialogCard}>
            <Text style={styles.dialogTitle}>Renomear álbum</Text>
            <TextInput style={styles.input} value={renameAlbumName} onChangeText={setRenameAlbumName} placeholder="Nome do álbum" placeholderTextColor="#9aa4b2" selectionColor="#2563eb" cursorColor="#2563eb" autoFocus />
            <View style={styles.dialogActions}>
              <Pressable style={styles.dialogCancel} onPress={() => setRenameAlbumId(null)}>
                <Text style={styles.dialogCancelText}>Cancelar</Text>
              </Pressable>
              <Pressable style={styles.dialogConfirm} onPress={confirmRenameAlbum}>
                <Text style={styles.dialogConfirmText}>Salvar</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>

      {!!slidePreparing && (
        <View style={styles.slidePrepare}>
          <ActivityIndicator size="large" color="#ffffff" />
          <Text style={styles.slidePrepareText}>{slidePreparing}</Text>
        </View>
      )}

      <Modal visible={!!slideshow} animationType="fade" onRequestClose={stopSlideshow}>
        <View style={styles.slideScreen}>
          {slideshow && (() => {
            const current = slideshow.items[slideIndex]
            if (!current) return null
            return (
              <>
                <Animated.View style={[styles.slideMedia, { opacity: slideOpacity }]}>
                  {current.media_type === 'video' ? (
                    <Video
                      source={{ uri: current.localUri }}
                      style={styles.slideMedia}
                      resizeMode={ResizeMode.CONTAIN}
                      shouldPlay
                      onPlaybackStatusUpdate={(status) => {
                        if (status.didJustFinish) advanceSlide(1)
                      }}
                    />
                  ) : (
                    <Image source={{ uri: current.localUri }} style={styles.slideMedia} resizeMode="contain" />
                  )}
                </Animated.View>
                <Pressable style={[styles.slideClose, { left: 20, right: undefined }]} onPress={() => advanceSlide(-1)}>
                  <Text style={styles.slideCloseText}>‹</Text>
                </Pressable>
                <Pressable style={styles.slideClose} onPress={stopSlideshow}>
                  <Text style={styles.slideCloseText}>✕</Text>
                </Pressable>
                <Pressable style={[styles.slideClose, { top: undefined, bottom: 90, right: 20 }]} onPress={() => advanceSlide(1)}>
                  <Text style={styles.slideCloseText}>›</Text>
                </Pressable>
                <View style={styles.slideCounter}>
                  <Text style={styles.slideCounterText}>{slideIndex + 1} / {slideshow.items.length}</Text>
                </View>
              </>
            )
          })()}
        </View>
      </Modal>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#f5f7fa' },
  tabContent: { flex: 1 },

  // Login
  loginScreen: { flex: 1, backgroundColor: '#0f172a', paddingHorizontal: 24, justifyContent: 'center' },
  loginBrand: { alignItems: 'center', marginBottom: 32 },
  loginLogo: { width: 72, height: 72, borderRadius: 20, backgroundColor: '#2563eb', alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  loginLogoText: { color: '#ffffff', fontSize: 36, fontWeight: '900' },
  loginTitle: { color: '#ffffff', fontSize: 30, fontWeight: '900', letterSpacing: 1 },
  loginSubtitle: { color: '#94a3b8', marginTop: 4 },
  loginCard: { backgroundColor: '#ffffff', borderRadius: 18, padding: 20 },
  inputLabel: { color: '#475569', fontWeight: '700', marginBottom: 6, marginTop: 4, fontSize: 13 },

  input: { height: 46, borderWidth: 1, borderColor: '#e2e8f0', borderRadius: 10, paddingHorizontal: 12, marginBottom: 10, backgroundColor: '#ffffff', color: '#0f172a', fontSize: 15 },
  primaryButton: { height: 48, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: '#2563eb', marginTop: 6 },
  primaryButtonText: { color: '#ffffff', fontWeight: '800', fontSize: 16 },
  status: { color: '#64748b', marginTop: 10, marginHorizontal: 16 },

  // Top bar
  topBar: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, paddingTop: 14, paddingBottom: 8 },
  topTitle: { fontSize: 28, fontWeight: '900', color: '#0f172a' },
  topSubtitle: { color: '#64748b', marginTop: 2, fontSize: 12 },
  iconButton: { marginLeft: 'auto', width: 42, height: 42, borderRadius: 21, backgroundColor: '#e8eefc', alignItems: 'center', justifyContent: 'center' },
  iconButtonText: { color: '#2563eb', fontSize: 20, fontWeight: '900' },

  // Chips / filters
  filterRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingBottom: 8, flexWrap: 'wrap' },
  chip: { height: 34, paddingHorizontal: 14, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: '#eef2f7', borderWidth: 1, borderColor: '#e2e8f0' },
  chipActive: { backgroundColor: '#2563eb', borderColor: '#2563eb' },
  chipText: { color: '#475569', fontWeight: '700' },
  chipTextActive: { color: '#ffffff' },
  resultCount: { marginLeft: 'auto', color: '#64748b', fontWeight: '700' },

  // Search
  searchWrap: { flexDirection: 'row', alignItems: 'center', marginHorizontal: 16, marginBottom: 10, paddingHorizontal: 12, height: 46, borderRadius: 12, backgroundColor: '#eef2f7', borderWidth: 1, borderColor: '#e2e8f0' },
  searchIcon: { fontSize: 15, marginRight: 8 },
  searchInput: { flex: 1, height: 46, color: '#0f172a', fontSize: 15 },
  clearSearch: { width: 26, height: 26, borderRadius: 13, alignItems: 'center', justifyContent: 'center', backgroundColor: '#d7deea' },
  clearSearchText: { color: '#475569', fontWeight: '900' },

  // Grid
  grid: { paddingHorizontal: 6, paddingBottom: 24, flexGrow: 1 },
  dateHeader: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 6, paddingTop: 14, paddingBottom: 6 },
  dateTitle: { color: '#0f172a', fontSize: 16, fontWeight: '900' },
  dateCount: { marginLeft: 'auto', color: '#94a3b8', fontWeight: '700', fontSize: 12 },
  tileRow: { flexDirection: 'row' },
  tile: { flex: 1, aspectRatio: 1, padding: 2 },
  thumb: { width: '100%', height: '100%', borderRadius: 8, backgroundColor: '#e2e8f0' },
  thumbMissing: { alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#e2e8f0' },
  thumbMissingText: { color: '#94a3b8', fontSize: 10, fontWeight: '800' },
  offlineBadge: { position: 'absolute', left: 6, top: 6, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, overflow: 'hidden', color: '#ffffff', backgroundColor: '#16a34a', fontSize: 9, fontWeight: '800' },
  videoBadge: { position: 'absolute', right: 6, bottom: 6, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, backgroundColor: 'rgba(15,23,42,0.82)' },
  videoBadgeText: { color: '#ffffff', fontSize: 10, fontWeight: '800' },

  // Empty
  emptyState: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingTop: 80, paddingHorizontal: 32 },
  emptyEmoji: { fontSize: 46, marginBottom: 12 },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: '#0f172a', marginBottom: 6 },
  emptyText: { color: '#64748b', textAlign: 'center' },

  // Date scrubber
  scrubber: { position: 'absolute', right: 0, top: 6, bottom: 6, width: 44 },
  scrubberTrack: { position: 'absolute', right: 20, top: SCRUB_THUMB / 2, bottom: SCRUB_THUMB / 2, width: 4, borderRadius: 2, backgroundColor: '#d7deea' },
  scrubberThumb: { position: 'absolute', right: 6, top: 0, width: 32, height: SCRUB_THUMB, borderRadius: 16, backgroundColor: '#2563eb', alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.25, shadowRadius: 5, shadowOffset: { width: 0, height: 2 }, elevation: 4 },
  scrubberThumbText: { color: '#ffffff', fontSize: 16, fontWeight: '900', letterSpacing: 1 },
  scrubOverlay: { position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, alignItems: 'center', justifyContent: 'center' },
  scrubOverlayCard: { paddingHorizontal: 32, paddingVertical: 22, borderRadius: 24, backgroundColor: 'rgba(15,23,42,0.72)', minWidth: 200, alignItems: 'center' },
  scrubOverlayText: { color: '#ffffff', fontWeight: '900', fontSize: 30, letterSpacing: 0.5, textAlign: 'center' },

  // Selection
  selectMark: { position: 'absolute', right: 8, top: 8, width: 22, height: 22, borderRadius: 11, borderWidth: 2, borderColor: '#ffffff', backgroundColor: 'rgba(15,23,42,0.35)', alignItems: 'center', justifyContent: 'center' },
  selectMarkActive: { backgroundColor: '#2563eb', borderColor: '#ffffff' },
  selectMarkText: { color: '#ffffff', fontSize: 12, fontWeight: '900' },
  selectionBar: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, paddingVertical: 10, backgroundColor: '#0f172a' },
  selectionText: { color: '#ffffff', fontWeight: '800', flex: 1 },
  selectionNew: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: '#1e293b' },
  selectionNewText: { color: '#93c5fd', fontWeight: '800' },
  selectionAction: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, backgroundColor: '#2563eb' },
  selectionActionText: { color: '#ffffff', fontWeight: '800' },
  selectionCancel: { paddingHorizontal: 12, paddingVertical: 8 },
  selectionCancelText: { color: '#94a3b8', fontWeight: '800' },

  // Albums
  albumRow: { flexDirection: 'row', alignItems: 'center', marginHorizontal: 16, marginBottom: 10, padding: 12, borderRadius: 14, backgroundColor: '#ffffff', borderWidth: 1, borderColor: '#eef2f7' },
  albumCover: { width: 54, height: 54, borderRadius: 10, backgroundColor: '#e2e8f0', marginRight: 12, alignItems: 'center', justifyContent: 'center' },
  albumCoverText: { fontSize: 22 },
  albumInfo: { flex: 1 },
  albumName: { color: '#0f172a', fontWeight: '800', fontSize: 16 },
  albumCount: { color: '#64748b', fontSize: 12, marginTop: 2 },
  albumPlay: { width: 40, height: 40, borderRadius: 20, backgroundColor: '#2563eb', alignItems: 'center', justifyContent: 'center', marginLeft: 8 },
  albumPlayText: { color: '#ffffff', fontSize: 16, fontWeight: '900' },
  albumEdit: { width: 40, height: 40, borderRadius: 20, backgroundColor: '#eef2f7', alignItems: 'center', justifyContent: 'center', marginLeft: 8 },
  albumEditText: { fontSize: 16 },
  newAlbumButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginHorizontal: 16, marginBottom: 12, height: 46, borderRadius: 12, borderWidth: 1, borderColor: '#c7d2fe', backgroundColor: '#eef2ff' },
  newAlbumButtonText: { color: '#2563eb', fontWeight: '800' },
  albumHeaderBar: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 12, paddingTop: 12 },
  backButton: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, backgroundColor: '#eef2f7' },
  backButtonText: { color: '#2563eb', fontWeight: '800' },

  // Slideshow
  slidePrepare: { position: 'absolute', top: 0, bottom: 0, left: 0, right: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(15,23,42,0.75)', zIndex: 20 },
  slidePrepareText: { color: '#ffffff', fontWeight: '800', marginTop: 12 },
  slideScreen: { flex: 1, backgroundColor: '#000000' },
  slideMedia: { flex: 1, width: '100%' },
  slideClose: { position: 'absolute', top: 40, right: 20, width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center', zIndex: 10 },
  slideCloseText: { color: '#ffffff', fontSize: 18, fontWeight: '900' },
  slideCounter: { position: 'absolute', bottom: 36, alignSelf: 'center', paddingHorizontal: 14, paddingVertical: 6, borderRadius: 12, backgroundColor: 'rgba(0,0,0,0.5)', zIndex: 10 },
  slideCounterText: { color: '#ffffff', fontWeight: '700' },
  sliderControlBtn: { paddingHorizontal: 16, paddingVertical: 10 },
  sliderControlText: { color: '#ffffff', fontSize: 22, fontWeight: '900' },
  stepperRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 4 },
  stepperButton: { width: 42, height: 42, borderRadius: 10, backgroundColor: '#e8eefc', alignItems: 'center', justifyContent: 'center' },
  stepperButtonText: { color: '#2563eb', fontSize: 20, fontWeight: '900' },
  stepperValue: { fontSize: 18, fontWeight: '800', color: '#0f172a', minWidth: 90, textAlign: 'center' },

  // Tree
  treeRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 6, paddingHorizontal: 12, paddingVertical: 12, borderRadius: 10, backgroundColor: '#ffffff', borderWidth: 1, borderColor: '#eef2f7' },
  treeIcon: { fontSize: 18, marginRight: 8 },
  treeLabel: { flex: 1, color: '#0f172a', fontWeight: '700', fontSize: 15 },
  treeCount: { color: '#64748b', fontWeight: '700', marginRight: 10 },
  treeChevron: { color: '#2563eb', fontSize: 16, fontWeight: '900', width: 18, textAlign: 'center', marginRight: 4 },
  treeOpen: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8, backgroundColor: '#eff4ff' },
  treeOpenText: { color: '#2563eb', fontWeight: '800', fontSize: 12 },
  treeSubRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 6, marginLeft: 26, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 10, backgroundColor: '#f8fafc', borderWidth: 1, borderColor: '#eef2f7' },
  treeBranch: { color: '#94a3b8', fontSize: 15, fontWeight: '900', width: 16 },
  treeSubLabel: { flex: 1, color: '#334155', fontWeight: '600', fontSize: 14 },

  // Dialog
  dialogBackdrop: { flex: 1, backgroundColor: 'rgba(15,23,42,0.55)', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28 },
  dialogCard: { width: '100%', backgroundColor: '#ffffff', borderRadius: 16, padding: 18 },
  dialogTitle: { fontSize: 18, fontWeight: '800', color: '#0f172a', marginBottom: 12 },
  dialogActions: { flexDirection: 'row', justifyContent: 'flex-end', gap: 10, marginTop: 6 },
  dialogCancel: { paddingHorizontal: 14, paddingVertical: 10 },
  dialogCancelText: { color: '#64748b', fontWeight: '800' },
  dialogConfirm: { paddingHorizontal: 18, paddingVertical: 10, borderRadius: 10, backgroundColor: '#2563eb' },
  dialogConfirmText: { color: '#ffffff', fontWeight: '800' },

  // Settings
  settingsScroll: { paddingBottom: 24 },
  accountCard: { flexDirection: 'row', alignItems: 'center', marginHorizontal: 16, padding: 16, borderRadius: 16, backgroundColor: '#ffffff', borderWidth: 1, borderColor: '#eef2f7' },
  avatar: { width: 52, height: 52, borderRadius: 26, backgroundColor: '#2563eb', alignItems: 'center', justifyContent: 'center', marginRight: 14 },
  avatarText: { color: '#ffffff', fontSize: 22, fontWeight: '900' },
  accountInfo: { flex: 1 },
  accountName: { color: '#0f172a', fontWeight: '800', fontSize: 16 },
  accountServer: { color: '#64748b', marginTop: 2, fontSize: 12 },
  sectionLabel: { color: '#94a3b8', fontWeight: '800', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, marginTop: 20, marginBottom: 8, marginHorizontal: 20 },
  settingsGroup: { marginHorizontal: 16, borderRadius: 16, backgroundColor: '#ffffff', borderWidth: 1, borderColor: '#eef2f7', overflow: 'hidden', padding: 12 },
  rowButton: { height: 44, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: '#e8eefc', marginTop: 4 },
  rowButtonText: { color: '#2563eb', fontWeight: '800' },
  rowItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: 14, paddingHorizontal: 4 },
  rowItemText: { color: '#0f172a', fontWeight: '700', fontSize: 15 },
  rowItemDanger: { color: '#dc2626' },
  rowItemHint: { marginLeft: 'auto', color: '#94a3b8', fontSize: 16 },
  rowDivider: { height: 1, backgroundColor: '#eef2f7' },

  versionText: { textAlign: 'center', color: '#94a3b8', fontSize: 12, marginTop: 16, marginBottom: 8 },

  // Tab bar
  tabBar: { flexDirection: 'row', height: 62, borderTopWidth: 1, borderTopColor: '#e5eaf1', backgroundColor: '#ffffff' },
  tabButton: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 2 },
  tabIcon: { fontSize: 20, opacity: 0.45 },
  tabIconActive: { opacity: 1 },
  tabLabel: { fontSize: 11, color: '#94a3b8', fontWeight: '700' },
  tabLabelActive: { color: '#2563eb' },

  // Viewer
  viewer: { flex: 1, backgroundColor: '#0b0f14' },
  viewerHeader: { height: 54, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 12 },
  closeButton: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: '#1e293b' },
  closeButtonText: { color: '#ffffff', fontWeight: '700' },
  viewerTitle: { flex: 1, color: '#e2e8f0', fontWeight: '700' },
  saveButton: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 10, backgroundColor: '#2563eb', minWidth: 92, alignItems: 'center' },
  saveButtonText: { color: '#ffffff', fontWeight: '800' },
  viewerStatus: { color: '#e2e8f0', marginTop: 10 },
  loadingFull: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  fullImage: { flex: 1, width: '100%' },
})