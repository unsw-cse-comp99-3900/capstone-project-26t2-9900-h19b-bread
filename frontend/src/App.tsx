import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useSelector } from 'react-redux';
import type { RootState } from './store';
import Login from './pages/Init/Login';
import Register from './pages/Init/Register';
import HomePage from './pages/Homepage/HomePage';

const ProtectedRoute = ({ element }: { element: React.ReactElement }) => {
  const token = useSelector((s: RootState) => s.auth.token);
  return token ? element : <Navigate to="/login" replace />;
};

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/"          element={<Navigate to="/login" replace />} />
        <Route path="/login"     element={<Login />} />
        <Route path="/register"  element={<Register />} />
        <Route path="/homepage"  element={<ProtectedRoute element={<HomePage />} />} />
        <Route path="*"          element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
