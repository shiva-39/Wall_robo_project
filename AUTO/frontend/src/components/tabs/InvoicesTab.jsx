import React from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { updateInvoice } from '../../store/slices/invoicesSlice'

export default function InvoicesTab(){
  const invoices = useSelector(s => s.invoices)
  const dispatch = useDispatch()

  const rows = invoices.allIds.map(id => invoices.byId[id])
  function onChange(id, field, value){
    dispatch(updateInvoice({ id, changes: { [field]: value } }))
  }

  function fieldMissing(inv) {
    // Required fields: invoice_number, invoice_date, total
    return !inv.invoice_number || !inv.invoice_date || !inv.total;
  }

  return (
    <div>
      <h2>Invoices</h2>
      <table className="data">
        <thead><tr><th>ID</th><th>Number</th><th>Date</th><th>Total</th></tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id} className={fieldMissing(r) ? 'row-missing' : ''}>
              <td>{r.id}</td>
              <td><input className={!r.invoice_number ? 'invalid' : ''} value={r.invoice_number||''} onChange={e=>onChange(r.id,'invoice_number',e.target.value)} /></td>
              <td><input className={!r.invoice_date ? 'invalid' : ''} value={r.invoice_date||''} onChange={e=>onChange(r.id,'invoice_date',e.target.value)} /></td>
              <td><input className={!r.total ? 'invalid' : ''} value={r.total||''} onChange={e=>onChange(r.id,'total',e.target.value)} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {invoices.allIds.length === 0 && <div className="hint">No invoices loaded yet — upload a file to extract.</div>}
    </div>
  )
}
