import { createSlice } from '@reduxjs/toolkit'

const invoicesSlice = createSlice({
  name: 'invoices',
  initialState: {
    byId: {},
    allIds: []
  },
  reducers: {
    setInvoices(state, action) {
      const invs = action.payload;
      state.byId = {};
      state.allIds = [];
      invs.forEach(i => { state.byId[i.id] = i; state.allIds.push(i.id) });
    },
    updateInvoice(state, action) {
      const { id, changes } = action.payload;
      if (!state.byId[id]) return;
      state.byId[id] = { ...state.byId[id], ...changes };
    }
  }
})

export const { setInvoices, updateInvoice } = invoicesSlice.actions
export default invoicesSlice.reducer
