import AsyncStorage from '@react-native-async-storage/async-storage'
import { Audio, ResizeMode, Video } from 'expo-av'
import * as FileSystem from 'expo-file-system'
import { StatusBar } from 'expo-status-bar'
import { useEffect, useMemo, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Image,
  Modal,
  Pressable,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native'

const SETTINGS_KEY = 'pics_mobile_settings'
const ITEMS_KEY = 'pics_mobile_items'
const THUMB_DIR = `${FileSystem.documentDirectory}thumbs/`
const FULL_DIR = `${FileSystem.documentDirectory}full/`
const ITEM_CACHE_LIMIT = 5000

function normalizeBaseUrl(value) {
  const trimmed = value.trim()
  const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `http://${trimmed}`
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

async function ensureDirectories() {
  await FileSystem.makeDirectoryAsync(THUMB_DIR, { intermediates: true })
  await FileSystem.makeDirectoryAsync(FULL_DIR, { intermediates: true })
}

async function persistItemCache(nextItems) {
  const cachedItems = nextItems.slice(0, ITEM_CACHE_LIMIT)
  try {
    await AsyncStorage.removeItem(ITEMS_KEY)
    if (cachedItems.length) {
      await AsyncStorage.setItem(ITEMS_KEY, JSON.stringify(cachedItems))
    }
  } catch (_) {
    await AsyncStorage.removeItem(ITEMS_KEY).catch(() => {})
    return 0
  }
  return cachedItems.length
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

export default function App() {
  const [baseUrl, setBaseUrl] = useState('http://klaused.tplinkdns.com:8000')
  const [email, setEmail] = useState('klaused@gmail.com')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [items, setItems] = useState([])
  const [syncToken, setSyncToken] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [syncStatus, setSyncStatus] = useState('')
  const [selected, setSelected] = useState(null)
  const [fullUri, setFullUri] = useState(null)
  const [fullLoading, setFullLoading] = useState(false)
  const [fullProgress, setFullProgress] = useState(0)

  useEffect(() => {
    Audio.setAudioModeAsync({ playsInSilentModeIOS: true }).catch(() => {})
    boot()
  }, [])

  async function boot() {
    await ensureDirectories()
    const [storedSettings, storedItems] = await Promise.all([
      AsyncStorage.getItem(SETTINGS_KEY),
      AsyncStorage.getItem(ITEMS_KEY),
    ])
    const cachedItems = storedItems ? JSON.parse(storedItems) : []
    if (cachedItems.length) {
      setItems(cachedItems)
    }
    if (storedSettings) {
      const parsed = JSON.parse(storedSettings)
      setBaseUrl(parsed.baseUrl || baseUrl)
      setEmail(parsed.email || '')
      setToken(parsed.token || '')
      setSyncToken(parsed.syncToken || null)
      if (parsed.token) {
        syncLibrary(parsed.token, parsed.baseUrl || baseUrl, parsed.syncToken || null, cachedItems)
      }
    }
  }

  async function persistSettings(next = {}) {
    const settings = {
      baseUrl,
      email,
      token,
      syncToken,
      ...next,
    }
    await AsyncStorage.setItem(SETTINGS_KEY, JSON.stringify(settings))
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

  async function syncLibrary(activeToken = token, activeBaseUrl = baseUrl, activeSyncToken = syncToken, seedItems = items) {
    if (!activeToken) return
    setSyncing(true)
    setSyncStatus('Sincronizando lista...')
    try {
      await ensureDirectories()
      let page = 1
      const requestedSince = activeSyncToken
      let nextSyncToken = activeSyncToken
      const itemMap = new Map(seedItems.map((item) => [item.id, item]))

      while (true) {
        const sinceParam = requestedSince ? `&since=${encodeURIComponent(requestedSince)}` : ''
        const manifestUrl = apiUrl(activeBaseUrl, `/media/sync/manifest?page=${page}&per_page=1000&size=300${sinceParam}`)
        const response = await fetchWithTimeout(manifestUrl, {
          headers: authHeaders(activeToken),
        })
        if (!response.ok) throw new Error(`Manifesto falhou (${response.status})`)
        const data = await response.json()
        const totalPages = Math.max(data.pages, 1)
        const totalItems = data.total || 0
        const processedBeforePage = (page - 1) * data.per_page
        setSyncStatus(`Lista: pagina ${page}/${totalPages} (${Math.min(processedBeforePage + data.items.length, totalItems)}/${totalItems} itens)`)

        for (const item of data.items) {
          const previous = itemMap.get(item.id)
          const localThumb = thumbPath(item)
          const thumbChanged = previous?.updated_at && previous.updated_at !== item.updated_at
          if (thumbChanged) {
            await FileSystem.deleteAsync(localThumb, { idempotent: true })
          }
          const localThumbnailUri = !thumbChanged && previous?.local_thumbnail_uri ? previous.local_thumbnail_uri : null
          const thumbnailFailed = !thumbChanged && previous?.thumbnail_failed ? true : false
          itemMap.set(item.id, { ...item, local_thumbnail_uri: localThumbnailUri, thumbnail_failed: thumbnailFailed })
        }

        nextSyncToken = data.sync_token
        if (!data.has_more) break
        page += 1
      }

      const nextItems = Array.from(itemMap.values()).sort((left, right) => {
        return (right.date_taken || '').localeCompare(left.date_taken || '')
      })
      setItems(nextItems)
      setSyncToken(nextSyncToken)
      const cachedCount = await persistItemCache(nextItems)
      await persistSettings({ token: activeToken, syncToken: nextSyncToken })
      const cacheText = nextItems.length > cachedCount ? `, ${cachedCount} em cache local` : ''
      setSyncStatus(`Lista pronta: ${nextItems.length} itens${cacheText}`)
    } catch (error) {
      Alert.alert('Sync', error.message)
      setSyncStatus('Sync interrompido')
    } finally {
      setSyncing(false)
    }
  }

  function markThumbnailFailed(id) {
    setItems((currentItems) => {
      const nextItems = currentItems.map((item) => item.id === id ? { ...item, thumbnail_failed: true } : item)
      persistItemCache(nextItems).catch(() => {})
      return nextItems
    })
  }

  async function openItem(item) {
    setSelected(item)
    setFullUri(null)
    setFullProgress(0)
    setFullLoading(true)
    try {
      const destination = fullPath(item)
      if (await fileExists(destination)) {
        setFullUri(destination)
      } else {
        const url = item.media_type === 'video' ? item.stream_url || item.file_url : item.file_url
        setFullUri(await downloadWithAuth(url, destination, token, setFullProgress))
      }
    } catch (error) {
      Alert.alert('Arquivo full', error.message)
      setSelected(null)
    } finally {
      setFullLoading(false)
    }
  }

  const groupedLabel = useMemo(() => {
    if (!items.length) return 'Nenhuma mídia offline ainda'
    const first = items[0]
    return `${items.length} itens offline · mais recente ${first.year || '--'}/${String(first.month || '--').padStart(2, '0')}`
  }, [items])

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style="dark" />
      <View style={styles.header}>
        <Text style={styles.title}>PICS</Text>
        <Text style={styles.subtitle}>{groupedLabel}</Text>
      </View>

      <View style={styles.panel}>
        <TextInput style={styles.input} value={baseUrl} onChangeText={setBaseUrl} placeholder="http://IP-do-servidor:8000" placeholderTextColor="#82796a" selectionColor="#1d5c53" cursorColor="#1d5c53" autoCapitalize="none" />
        <TextInput style={styles.input} value={email} onChangeText={setEmail} placeholder="email" placeholderTextColor="#82796a" selectionColor="#1d5c53" cursorColor="#1d5c53" autoCapitalize="none" keyboardType="email-address" />
        <TextInput style={styles.input} value={password} onChangeText={setPassword} placeholder="senha" placeholderTextColor="#82796a" selectionColor="#1d5c53" cursorColor="#1d5c53" secureTextEntry textContentType="password" autoComplete="password" autoCorrect={false} />
        <View style={styles.actions}>
          <Pressable style={styles.primaryButton} onPress={login}>
            <Text style={styles.primaryButtonText}>Entrar e sincronizar</Text>
          </Pressable>
          <Pressable style={styles.secondaryButton} onPress={() => syncLibrary()} disabled={!token || syncing}>
            <Text style={styles.secondaryButtonText}>{syncing ? 'Sincronizando' : 'Sync'}</Text>
          </Pressable>
        </View>
        <Text style={styles.status}>{syncStatus}</Text>
      </View>

      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        numColumns={3}
        contentContainerStyle={styles.grid}
        renderItem={({ item }) => (
          <Pressable style={styles.tile} onPress={() => openItem(item)}>
            {item.thumbnail_failed ? (
              <View style={[styles.thumb, styles.thumbMissing]}>
                <Text style={styles.thumbMissingText}>SEM THUMB</Text>
              </View>
            ) : (
              <Image source={{ uri: item.local_thumbnail_uri || item.thumbnail_url, headers: authHeaders(token) }} style={styles.thumb} onError={() => markThumbnailFailed(item.id)} />
            )}
            {item.media_type === 'video' && <Text style={styles.videoBadge}>VIDEO</Text>}
          </Pressable>
        )}
      />

      <Modal visible={!!selected} animationType="slide" onRequestClose={() => setSelected(null)}>
        <SafeAreaView style={styles.viewer}>
          <View style={styles.viewerHeader}>
            <Pressable onPress={() => setSelected(null)} style={styles.closeButton}>
              <Text style={styles.closeButtonText}>Fechar</Text>
            </Pressable>
            <Text style={styles.viewerTitle} numberOfLines={1}>{selected?.filename}</Text>
          </View>
          {fullLoading && (
            <View style={styles.loadingFull}>
              <ActivityIndicator size="large" />
              <Text style={styles.status}>Baixando arquivo full {Math.round(fullProgress * 100)}%</Text>
            </View>
          )}
          {!fullLoading && fullUri && selected?.media_type === 'image' && <Image source={{ uri: fullUri }} style={styles.fullImage} resizeMode="contain" />}
          {!fullLoading && fullUri && selected?.media_type === 'video' && (
            <Video source={{ uri: fullUri }} style={styles.fullImage} useNativeControls resizeMode={ResizeMode.CONTAIN} />
          )}
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  )
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#f4f1ea' },
  header: { paddingHorizontal: 18, paddingTop: 12, paddingBottom: 8 },
  title: { fontSize: 34, fontWeight: '800', color: '#18332f', letterSpacing: 0 },
  subtitle: { color: '#50645f', marginTop: 2 },
  panel: { margin: 12, padding: 12, borderRadius: 8, backgroundColor: '#fffaf0', borderWidth: 1, borderColor: '#ded6c7' },
  input: { height: 42, borderWidth: 1, borderColor: '#cbc2b0', borderRadius: 6, paddingHorizontal: 10, marginBottom: 8, backgroundColor: '#ffffff', color: '#18332f' },
  actions: { flexDirection: 'row', gap: 8 },
  primaryButton: { flex: 1, height: 42, borderRadius: 6, alignItems: 'center', justifyContent: 'center', backgroundColor: '#1d5c53' },
  primaryButtonText: { color: '#ffffff', fontWeight: '700' },
  secondaryButton: { width: 84, height: 42, borderRadius: 6, alignItems: 'center', justifyContent: 'center', backgroundColor: '#d6e7df' },
  secondaryButtonText: { color: '#17443e', fontWeight: '700' },
  status: { color: '#5d665f', marginTop: 8 },
  grid: { paddingHorizontal: 8, paddingBottom: 24 },
  tile: { width: '33.333%', aspectRatio: 1, padding: 3 },
  thumb: { width: '100%', height: '100%', borderRadius: 6, backgroundColor: '#d9d2c4' },
  thumbMissing: { alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#c9beab' },
  thumbMissingText: { color: '#6d6255', fontSize: 10, fontWeight: '800' },
  videoBadge: { position: 'absolute', right: 7, bottom: 7, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, overflow: 'hidden', color: '#ffffff', backgroundColor: '#18332f', fontSize: 10, fontWeight: '800' },
  viewer: { flex: 1, backgroundColor: '#121614' },
  viewerHeader: { height: 54, flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 12 },
  closeButton: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 6, backgroundColor: '#f4f1ea' },
  closeButtonText: { color: '#18332f', fontWeight: '700' },
  viewerTitle: { flex: 1, color: '#f4f1ea', fontWeight: '700' },
  loadingFull: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  fullImage: { flex: 1, width: '100%' },
})