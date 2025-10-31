import React from 'react'
import UploadPanel from './components/UploadPanel'
import Tabs from './components/Tabs'
import MissingFieldsPanel from './components/MissingFieldsPanel'

export default function App() {
  return (
    <div className="app">
      <header>
        <h1>Swipe — Automated Data Extraction & Invoice Management</h1>
      </header>
      <main>
        <UploadPanel />
        <MissingFieldsPanel />
        <Tabs />
      </main>
    </div>
  )
}
