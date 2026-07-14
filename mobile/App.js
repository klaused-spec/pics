import AsyncStorage from '@react-native-async-storage/async-storage'
import { Audio, ResizeMode, Video } from 'expo-av'
import * as FileSystem from 'expo-file-system'
import { StatusBar } from 'expo-status-bar'
import { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Image,
  Modal,
  PanResponder,
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

export default function App() {
  const [baseUrl, setBaseUrl] = useState('http://klaused.tplinkdns.com:8000')
  const [email, setEmail] = useState('klaused@gmail.com')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [items, setItems] = useState([])
  const [syncToken, setSyncToken] = useState(null)
  const [syncing, setSyncing] = useState(false)
  const [syncStatus, setSyncStatus] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [mediaFilter, setMediaFilter] = useState('all')
  const [offlineOnly, setOfflineOnly] = useState(false)
  const [cachedFullIds, setCachedFullIds] = useState(new Set())
  const [activeTab, setActiveTab] = useState('photos')
  const [selected, setSelected] = useState(null)
  const [fullUri, setFullUri] = useState(null)
  const [fullLoading, setFullLoading] = useState(false)
  const [fullProgress, setFullProgress] = useState(0)
  const [scrubLabel, setScrubLabel] = useState('')
  const [scrubbing, setScrubbing] = useState(false)
  const listRef = useRef(null)
  const scrubTrackRef = useRef({ y: 0, height: 0 })
  const anchorsRef = useRef([])

  useEffect(() => {
    Audio.setAudioModeAsync({ playsInSilentModeIOS: true }).catch(() => {})
    boot()
  }, [])

  async function boot() {
    await ensureDirectories()
    await refreshCachedFullIds()
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

  async function refreshCachedFullIds() {
    try {
      const files = await FileSystem.readDirectoryAsync(FULL_DIR)
      const ids = files.map((file) => file.match(/^(\d+)_/)?.[1]).filter(Boolean).map(Number)
      setCachedFullIds(new Set(ids))
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
        markFullCached(item.id)
      } else {
        const url = item.media_type === 'video' ? item.stream_url || item.file_url : item.file_url
        const downloadedUri = await downloadWithAuth(url, destination, token, setFullProgress)
        setFullUri(downloadedUri)
        markFullCached(item.id)
      }
    } catch (error) {
      Alert.alert('Arquivo full', error.message)
      setSelected(null)
    } finally {
      setFullLoading(false)
    }
  }

  async function clearOfflineFiles() {
    try {
      await FileSystem.deleteAsync(FULL_DIR, { idempotent: true })
      await FileSystem.deleteAsync(THUMB_DIR, { idempotent: true })
      await ensureDirectories()
      setCachedFullIds(new Set())
      const nextItems = items.map((item) => ({ ...item, local_thumbnail_uri: null, thumbnail_failed: false }))
      setItems(nextItems)
      await persistItemCache(nextItems)
      setSyncStatus('Arquivos offline removidos')
    } catch (error) {
      Alert.alert('Limpar offline', error.message)
    }
  }

  function confirmClearOfflineFiles() {
    Alert.alert('Limpar offline', 'Apagar arquivos full e thumbnails baixados deste celular?', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Limpar', style: 'destructive', onPress: clearOfflineFiles },
    ])
  }

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

    return { rows, anchors, total: visibleItems.length }
  }, [cachedFullIds, deferredSearchQuery, items, mediaFilter, offlineOnly])

  function renderTile(item) {
    return (
      <Pressable key={item.id} style={styles.tile} onPress={() => openItem(item)}>
        {item.thumbnail_failed ? (
          <View style={[styles.thumb, styles.thumbMissing]}>
            <Text style={styles.thumbMissingText}>SEM THUMB</Text>
          </View>
        ) : (
          <Image source={{ uri: item.local_thumbnail_uri || item.thumbnail_url, headers: authHeaders(token) }} style={styles.thumb} onError={() => markThumbnailFailed(item.id)} />
        )}
        {cachedFullIds.has(item.id) && <Text style={styles.offlineBadge}>OFFLINE</Text>}
        {item.media_type === 'video' && <Text style={styles.videoBadge}>VIDEO</Text>}
      </Pressable>
    )
  }

  anchorsRef.current = gallery.anchors

  function scrubToPosition(pageY) {
    const { y, height } = scrubTrackRef.current
    const anchors = anchorsRef.current
    if (!height || !anchors.length) return
    const ratio = Math.max(0, Math.min(1, (pageY - y) / height))
    const index = Math.min(anchors.length - 1, Math.round(ratio * (anchors.length - 1)))
    const anchor = anchors[index]
    if (!anchor) return
    setScrubLabel(anchor.title)
    listRef.current?.scrollToIndex({ index: anchor.rowIndex, animated: false, viewPosition: 0 })
  }

  const scrubViewRef = useRef(null)

  function measureTrack() {
    scrubViewRef.current?.measureInWindow((x, y, width, height) => {
      scrubTrackRef.current = { y, height }
    })
  }

  const scrubResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: (evt) => {
        setScrubbing(true)
        scrubToPosition(evt.nativeEvent.pageY)
      },
      onPanResponderMove: (evt) => {
        scrubToPosition(evt.nativeEvent.pageY)
      },
      onPanResponderRelease: () => setScrubbing(false),
      onPanResponderTerminate: () => setScrubbing(false),
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
        <View style={styles.dateHeader}>
          <Text style={styles.dateTitle}>{item.title}</Text>
          <Text style={styles.dateCount}>{item.count} itens</Text>
        </View>
      ) : (
        <View style={styles.tileRow}>
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
        <View style={styles.scrubberThumb} pointerEvents="none">
          <Text style={styles.scrubberThumbText}>◆</Text>
        </View>
      </View>
    )}
    {scrubbing && !!scrubLabel && (
      <View style={[styles.scrubberBubble, { top: '46%' }]} pointerEvents="none">
        <Text style={styles.scrubberBubbleText}>{scrubLabel}</Text>
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
        </View>
      </SafeAreaView>
    )
  }

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style="dark" />

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
                <Pressable style={styles.rowItem} onPress={confirmClearOfflineFiles}>
                  <Text style={[styles.rowItemText, styles.rowItemDanger]}>Limpar arquivos offline</Text>
                  <Text style={styles.rowItemHint}>🗑️</Text>
                </Pressable>
              </View>
              {!!syncStatus && <Text style={styles.status}>{syncStatus}</Text>}

              <Text style={styles.sectionLabel}>Conta</Text>
              <View style={styles.settingsGroup}>
                <Pressable style={styles.rowItem} onPress={confirmLogout}>
                  <Text style={[styles.rowItemText, styles.rowItemDanger]}>Sair da conta</Text>
                  <Text style={styles.rowItemHint}>⎋</Text>
                </Pressable>
              </View>
            </View>
          )}
        />
      )}

      <View style={styles.tabBar}>
        {[
          ['photos', 'Fotos', '🖼️'],
          ['search', 'Buscar', '🔍'],
          ['settings', 'Config', '⚙️'],
        ].map(([value, label, icon]) => (
          <Pressable key={value} style={styles.tabButton} onPress={() => setActiveTab(value)}>
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
          </View>
          {fullLoading && (
            <View style={styles.loadingFull}>
              <ActivityIndicator size="large" color="#ffffff" />
              <Text style={styles.viewerStatus}>Baixando arquivo full {Math.round(fullProgress * 100)}%</Text>
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
  videoBadge: { position: 'absolute', right: 6, bottom: 6, paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4, overflow: 'hidden', color: '#ffffff', backgroundColor: '#0f172a', fontSize: 9, fontWeight: '800' },

  // Empty
  emptyState: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingTop: 80, paddingHorizontal: 32 },
  emptyEmoji: { fontSize: 46, marginBottom: 12 },
  emptyTitle: { fontSize: 18, fontWeight: '800', color: '#0f172a', marginBottom: 6 },
  emptyText: { color: '#64748b', textAlign: 'center' },

  // Date scrubber
  scrubber: { position: 'absolute', right: 3, top: 0, bottom: 0, width: 34, justifyContent: 'center', alignItems: 'center' },
  scrubberTrack: { flex: 1, marginVertical: 12, justifyContent: 'space-between', alignItems: 'center' },
  scrubberThumb: { width: 30, height: 30, borderRadius: 15, backgroundColor: '#2563eb', alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.2, shadowRadius: 4, shadowOffset: { width: 0, height: 2 }, elevation: 3 },
  scrubberThumbText: { color: '#ffffff', fontSize: 9, fontWeight: '900' },
  scrubberBubble: { position: 'absolute', right: 42, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 12, backgroundColor: '#0f172a' },
  scrubberBubbleText: { color: '#ffffff', fontWeight: '900', fontSize: 15 },

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
  viewerStatus: { color: '#e2e8f0', marginTop: 10 },
  loadingFull: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  fullImage: { flex: 1, width: '100%' },
})