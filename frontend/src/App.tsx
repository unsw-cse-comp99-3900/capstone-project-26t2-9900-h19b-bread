import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import type { RootState } from './store';
import Login from './pages/Init/Login';
import Register from './pages/Init/Register';
import HomePage from './pages/Homepage/HomePage';
import ApiDetailPage from './pages/ApiDetail/ApiDetailPage';
import SchemaMappingPage from './pages/SchemaMapping/SchemaMappingPage';

const ProtectedRoute = ({ element }: { element: React.ReactElement }) => {
  const token = useSelector((s: RootState) => s.auth.token);
  return token ? element : <Navigate to="/login" replace />;
};

const GuestRoute = ({ element }: { element: React.ReactElement }) => {
  const token = useSelector((s: RootState) => s.auth.token);
  return token ? <Navigate to="/homepage" replace /> : element;
};

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/"          element={<GuestRoute element={<Navigate to="/login" replace />} />} />
        <Route path="/login"     element={<GuestRoute element={<Login />} />} />
        <Route path="/register"  element={<GuestRoute element={<Register />} />} />
        <Route path="/homepage"  element={<ProtectedRoute element={<HomePage />} />} />
        <Route path="/apis/:id"  element={<ProtectedRoute element={<ApiDetailPage />} />} />
        <Route path="/apis/:id/mapping" element={<ProtectedRoute element={<SchemaMappingPage />} />} />
        <Route path="/schema-mapping" element={<ProtectedRoute element={<SchemaMappingPage />} />} />
        <Route path="*"          element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
