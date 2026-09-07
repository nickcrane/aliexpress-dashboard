// Firebase Authentication only -- no Firestore/Storage/Analytics, so this
// stays a thin wrapper around just the `firebase/auth` subpackage. Config
// comes from a real Firebase project's Web app settings (see README);
// these values are not secret in the way an API key normally is (they're
// meant to be public in a browser bundle -- Firebase's actual security
// boundary is its server-side rules/provider config, not this object).
import { initializeApp } from "firebase/app";
import { type Auth, getAuth } from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string,
};

// getAuth() throws (crashing the whole app with a blank page) rather than
// failing gracefully when the config is missing/invalid -- confirmed live.
// Checked upfront so the UI can show a clear setup message instead, same
// approach as the Bootstrap app's require_login check for unconfigured
// Google credentials.
export const isFirebaseConfigured = Boolean(
  firebaseConfig.apiKey && firebaseConfig.authDomain && firebaseConfig.projectId && firebaseConfig.appId,
);

export const auth: Auth | null = isFirebaseConfigured ? getAuth(initializeApp(firebaseConfig)) : null;
