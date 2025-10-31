import React, { useState } from 'react'
import InvoicesTab from './tabs/InvoicesTab'
import ProductsTab from './tabs/ProductsTab'
import CustomersTab from './tabs/CustomersTab'

export default function Tabs(){
  const [tab, setTab] = useState('invoices')
  return (
    <div className="tabs">
      <nav>
        <button onClick={() => setTab('invoices')}>Invoices</button>
        <button onClick={() => setTab('products')}>Products</button>
        <button onClick={() => setTab('customers')}>Customers</button>
      </nav>
      <section>
        {tab === 'invoices' && <InvoicesTab />}
        {tab === 'products' && <ProductsTab />}
        {tab === 'customers' && <CustomersTab />}
      </section>
    </div>
  )
}
