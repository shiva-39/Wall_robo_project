import { createSlice } from '@reduxjs/toolkit'

const customersSlice = createSlice({
  name: 'customers',
  initialState: {
    byId: {},
    allIds: []
  },
  reducers: {
    setCustomers(state, action) {
      const items = action.payload;
      state.byId = {};
      state.allIds = [];
      items.forEach(c => { state.byId[c.id] = c; state.allIds.push(c.id) });
    },
    updateCustomer(state, action) {
      const { id, changes } = action.payload;
      if (!state.byId[id]) return;
      state.byId[id] = { ...state.byId[id], ...changes };
    }
  }
})

export const { setCustomers, updateCustomer } = customersSlice.actions
export default customersSlice.reducer
