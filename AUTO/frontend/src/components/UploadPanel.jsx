import React, { useState } from 'react'
import axios from 'axios'
import { useDispatch } from 'react-redux'
import { setInvoices } from '../store/slices/invoicesSlice'
import { setProducts } from '../store/slices/productsSlice'
import { setCustomers } from '../store/slices/customersSlice'

export default function UploadPanel() {
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState('')
  const dispatch = useDispatch()

  async function upload() {
    if (!file) return setStatus('No file selected')
    setStatus('Uploading...')
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await axios.post('/api/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' }})
      const data = res.data.data
      setStatus('Extraction complete')
      // dispatch to store
      if (data.invoices) dispatch(setInvoices(data.invoices))
      if (data.products) dispatch(setProducts(data.products))
      if (data.customers) dispatch(setCustomers(data.customers))
    } catch (err) {
      console.error(err)
      setStatus('Error: ' + (err?.response?.data?.error || err.message))
    }
  }

  return (
    <div className="upload-panel">
      <input type="file" onChange={e => setFile(e.target.files[0])} />
      <button onClick={upload}>Upload & Extract</button>
      <div className="status">{status}</div>
    </div>
  )
}
