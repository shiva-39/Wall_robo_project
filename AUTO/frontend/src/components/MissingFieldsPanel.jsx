import React, { useState, useEffect } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { updateInvoice } from '../store/slices/invoicesSlice'

export default function MissingFieldsPanel(){
  const invoicesState = useSelector(s => s.invoices)
  const dispatch = useDispatch()
  const rows = invoicesState.allIds.map(id => invoicesState.byId[id])

  const [values, setValues] = useState({})

  useEffect(() => {
    // Initialize local input values for missing fields
    const map = {}
    rows.forEach(inv => {
      const missing = []
      if (!inv.invoice_number) missing.push('invoice_number')
      if (!inv.invoice_date) missing.push('invoice_date')
      if (!inv.total && inv.total !== 0) missing.push('total')
      if (missing.length) {
        map[inv.id] = map[inv.id] || {}
        missing.forEach(f => { map[inv.id][f] = inv[f] || '' })
      }
    })
    setValues(map)
  }, [invoicesState])

  function missingFields(inv){
    const missing = []
    if (!inv.invoice_number) missing.push('invoice_number')
    if (!inv.invoice_date) missing.push('invoice_date')
    if (!inv.total && inv.total !== 0) missing.push('total')
    return missing
  }

  function onChangeLocal(invId, field, val){
    setValues(v => ({ ...v, [invId]: { ...(v[invId]||{}), [field]: val } }))
  }

  function onUpdate(invId, field){
    const val = values?.[invId]?.[field]
    if (val == null) return
    dispatch(updateInvoice({ id: invId, changes: { [field]: val } }))
  }

  const items = rows.map(r => ({ id: r.id, missing: missingFields(r) })).filter(x => x.missing.length)

  if (!items.length) return <div className="missing-panel">All required fields present.</div>

  return (
    <div className="missing-panel">
      <h3>Missing fields</h3>
      <ul>
        {items.map(it => (
          <li key={it.id} style={{ marginBottom: 12 }}>
            <div><strong>{it.id}</strong>: {it.missing.join(', ')}</div>
            <div className="actions" style={{ marginTop: 6 }}>
              {it.missing.includes('invoice_number') && (
                <span style={{ marginRight: 8 }}>
                  <input placeholder="Invoice number" value={values?.[it.id]?.invoice_number || ''} onChange={e => onChangeLocal(it.id,'invoice_number', e.target.value)} />
                  <button onClick={() => onUpdate(it.id,'invoice_number')}>Update</button>
                </span>
              )}
              {it.missing.includes('invoice_date') && (
                <span style={{ marginRight: 8 }}>
                  <input type="date" value={values?.[it.id]?.invoice_date || ''} onChange={e => onChangeLocal(it.id,'invoice_date', e.target.value)} />
                  <button onClick={() => onUpdate(it.id,'invoice_date')}>Update</button>
                </span>
              )}
              {it.missing.includes('total') && (
                <span style={{ marginRight: 8 }}>
                  <input placeholder="Total amount" value={values?.[it.id]?.total || ''} onChange={e => onChangeLocal(it.id,'total', e.target.value)} />
                  <button onClick={() => onUpdate(it.id,'total')}>Update</button>
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
      <small>Use these quick editors to fill missing invoice fields. Changes apply to the Redux store and will reflect in the invoice table.</small>
    </div>
  )
}
