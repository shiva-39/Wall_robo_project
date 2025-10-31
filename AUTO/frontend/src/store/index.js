import { configureStore } from '@reduxjs/toolkit'
import invoicesReducer from './slices/invoicesSlice'
import productsReducer from './slices/productsSlice'
import customersReducer from './slices/customersSlice'

export default configureStore({
  reducer: {
    invoices: invoicesReducer,
    products: productsReducer,
    customers: customersReducer
  }
})
