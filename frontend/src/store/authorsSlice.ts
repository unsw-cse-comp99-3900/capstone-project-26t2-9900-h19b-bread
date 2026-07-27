import { createAsyncThunk, createSlice } from '@reduxjs/toolkit';
import { getAuthors, type AuthorListItem } from '../services/submission';
import { logout } from './authSlice';

interface AuthorsState {
  items:     AuthorListItem[];
  status:    'idle' | 'loading' | 'succeeded' | 'failed';
  error:     string | null;
  fetchedAt: number | null;
}

const initialState: AuthorsState = {
  items:     [],
  status:    'idle',
  error:     null,
  fetchedAt: null,
};

export const fetchAuthors = createAsyncThunk(
  'authors/fetchAuthors',
  async () => getAuthors(),
);

const authorsSlice = createSlice({
  name: 'authors',
  initialState,
  reducers: {
    clearAuthors(state) {
      state.items = [];
      state.status = 'idle';
      state.error = null;
      state.fetchedAt = null;
    },
  },
  extraReducers: builder => {
    builder
      .addCase(fetchAuthors.pending, state => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchAuthors.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.items = action.payload;
        state.fetchedAt = Date.now();
      })
      .addCase(fetchAuthors.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.error.message ?? 'Failed to load authors';
      })
      .addCase(logout, state => {
        state.items = [];
        state.status = 'idle';
        state.error = null;
        state.fetchedAt = null;
      });
  },
});

export const { clearAuthors } = authorsSlice.actions;
export default authorsSlice.reducer;
