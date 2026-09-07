import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import {
  createUserWithEmailAndPassword,
  FacebookAuthProvider,
  GoogleAuthProvider,
  OAuthProvider,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut as firebaseSignOut,
  type User,
} from "firebase/auth";

import { auth } from "./firebase";

// AuthProvider is only ever rendered by App.tsx after confirming
// isFirebaseConfigured, so `auth` is never actually null at this point.
const requiredAuth = auth!;

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  signInWithGoogle: () => Promise<void>;
  signInWithFacebook: () => Promise<void>;
  signInWithApple: () => Promise<void>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  signUpWithEmail: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => onAuthStateChanged(requiredAuth, (u) => {
    setUser(u);
    setLoading(false);
  }), []);

  const value: AuthContextValue = {
    user,
    loading,
    signInWithGoogle: async () => {
      await signInWithPopup(requiredAuth, new GoogleAuthProvider());
    },
    signInWithFacebook: async () => {
      await signInWithPopup(requiredAuth, new FacebookAuthProvider());
    },
    signInWithApple: async () => {
      await signInWithPopup(requiredAuth, new OAuthProvider("apple.com"));
    },
    signInWithEmail: async (email, password) => {
      await signInWithEmailAndPassword(requiredAuth, email, password);
    },
    signUpWithEmail: async (email, password) => {
      await createUserWithEmailAndPassword(requiredAuth, email, password);
    },
    signOut: () => firebaseSignOut(requiredAuth),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
