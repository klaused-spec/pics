import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import ProtectedRoute from './components/ProtectedRoute'
import Login from './pages/Login'
import Gallery from './pages/Gallery'
import AlbumDetail from './pages/AlbumDetail'
import MediaDetail from './pages/MediaDetail'
import Search from './pages/Search'
import Persons from './pages/Persons'
import PersonDetail from './pages/PersonDetail'
import FaceReview from './pages/FaceReview'
import Slideshow from './pages/Slideshow'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import Duplicates from './pages/Duplicates'
import Maintenance from './pages/Maintenance'
import MobileApps from './pages/MobileApps'
import Users from './pages/Users'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={
        <ProtectedRoute>
          <Layout />
        </ProtectedRoute>
      }>
        <Route index element={<Dashboard />} />
        <Route path="gallery" element={<Gallery />} />
        <Route path="albums/:id" element={<AlbumDetail />} />
        <Route path="media/:id" element={<MediaDetail />} />
        <Route path="search" element={<Search />} />
        <Route path="persons" element={<Persons />} />
        <Route path="persons/review" element={<FaceReview />} />
        <Route path="persons/:id" element={<PersonDetail />} />
        <Route path="settings" element={<Settings />} />
        <Route path="duplicates" element={<Duplicates />} />
        <Route path="maintenance" element={<Maintenance />} />
        <Route path="mobile" element={<MobileApps />} />
        <Route path="users" element={<Users />} />
        <Route path="dashboard" element={<Dashboard />} />
      </Route>
      <Route path="/slideshow" element={
        <ProtectedRoute>
          <Slideshow />
        </ProtectedRoute>
      } />
    </Routes>
  )
}

export default App
