import React from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { updateCustomer } from '../../store/slices/customersSlice'

export default function CustomersTab(){
  const customers = useSelector(s => s.customers)
  const dispatch = useDispatch()
  const rows = customers.allIds.map(id => customers.byId[id])
  function onChange(id, field, value){
    dispatch(updateCustomer({ id, changes: { [field]: value } }))
  }
  return (
    <div>
      <h2>Customers</h2>
      <table className="data">
        <thead><tr><th>ID</th><th>Name</th><th>Contact</th><th>Address</th></tr></thead>
        <tbody>
          {rows.map(c => (
            <tr key={c.id} className={!c.name ? 'row-missing' : ''}>
              <td>{c.id}</td>
              <td><input className={!c.name ? 'invalid' : ''} value={c.name||''} onChange={e=>onChange(c.id,'name',e.target.value)} /></td>
              <td><input value={c.contact||''} onChange={e=>onChange(c.id,'contact',e.target.value)} /></td>
              <td><input value={c.address||''} onChange={e=>onChange(c.id,'address',e.target.value)} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
