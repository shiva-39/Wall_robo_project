import React from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { updateProduct } from '../../store/slices/productsSlice'
import { updateInvoice } from '../../store/slices/invoicesSlice'

export default function ProductsTab(){
  const products = useSelector(s => s.products)
  const invoices = useSelector(s => s.invoices)
  const dispatch = useDispatch()
  const rows = products.allIds.map(id => products.byId[id])
  function onChange(id, field, value){
    // Keep a simple sync: if product name changes, update invoice line_items descriptions that match old name
    const p = products.byId[id];
    const oldName = p?.name || '';
    dispatch(updateProduct({ id, changes: { [field]: value } }))
    if (field === 'name') {
      // update invoices where line_items.description === oldName
      const invoicesState = storeInvoices();
      invoicesState.allIds.forEach(invId => {
        const inv = invoicesState.byId[invId];
        if (!inv || !inv.line_items) return;
        let changed = false;
        const newLineItems = inv.line_items.map(li => {
          if (String(li.description).trim() === String(oldName).trim()) {
            changed = true;
            return { ...li, description: value };
          }
          return li;
        });
        if (changed) {
          dispatch(updateInvoice({ id: invId, changes: { line_items: newLineItems } }));
        }
      });
    }
  }

  // helper to get invoices from store
  const storeInvoices = () => {
    // We capture current invoices from selector
    return invoices;
  }
  return (
    <div>
      <h2>Products</h2>
      <table className="data">
        <thead><tr><th>ID</th><th>Name</th><th>SKU</th><th>Price</th></tr></thead>
        <tbody>
          {rows.map(p => (
            <tr key={p.id}>
              <td>{p.id}</td>
              <td><input value={p.name||''} onChange={e=>onChange(p.id,'name',e.target.value)} /></td>
              <td><input value={p.sku||''} onChange={e=>onChange(p.id,'sku',e.target.value)} /></td>
              <td><input value={p.price||''} onChange={e=>onChange(p.id,'price',e.target.value)} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
