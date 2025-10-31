import { createSlice } from '@reduxjs/toolkit'

const productsSlice = createSlice({
  name: 'products',
  initialState: {
    byId: {},
    allIds: []
  },
  reducers: {
    setProducts(state, action) {
      const items = action.payload;
      state.byId = {};
      state.allIds = [];
      items.forEach(p => { state.byId[p.id] = p; state.allIds.push(p.id) });
    },
    updateProduct(state, action) {
      const { id, changes } = action.payload;
      if (!state.byId[id]) return;
      state.byId[id] = { ...state.byId[id], ...changes };
    }
  }
})

export const { setProducts, updateProduct } = productsSlice.actions
export default productsSlice.reducer
