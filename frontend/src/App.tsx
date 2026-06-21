import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Init/Login";
import Register from "./pages/Init/Register";
function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Navigate to="/login" />} />
        <Route path="/register" element={<Register />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
