import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider, useAuth } from "./AuthContext";
import { NavBar } from "./components/NavBar";
import { isFirebaseConfigured } from "./firebase";
import { LoginPage } from "./pages/LoginPage";
import { MomentumPage } from "./pages/MomentumPage";
import { ProductsPage } from "./pages/ProductsPage";
import { ShortlistsPage } from "./pages/ShortlistsPage";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <>
      <NavBar />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <ProductsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/momentum"
          element={
            <RequireAuth>
              <MomentumPage />
            </RequireAuth>
          }
        />
        <Route
          path="/shortlists"
          element={
            <RequireAuth>
              <ShortlistsPage />
            </RequireAuth>
          }
        />
      </Routes>
    </>
  );
}

function NotConfigured() {
  return (
    <div style={{ display: "flex", justifyContent: "center", padding: "3rem 1rem" }}>
      <div style={{ maxWidth: "28rem", textAlign: "center" }}>
        <h1 style={{ fontSize: "1.2rem" }}>Sign-in isn't configured yet</h1>
        <p>
          Set <code>VITE_FIREBASE_API_KEY</code>, <code>VITE_FIREBASE_AUTH_DOMAIN</code>,{" "}
          <code>VITE_FIREBASE_PROJECT_ID</code>, and <code>VITE_FIREBASE_APP_ID</code> in{" "}
          <code>.env.local</code> (see README).
        </p>
      </div>
    </div>
  );
}

export default function App() {
  if (!isFirebaseConfigured) return <NotConfigured />;

  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
