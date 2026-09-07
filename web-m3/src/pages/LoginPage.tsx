import "@material/web/textfield/outlined-text-field.js";
import "@material/web/button/filled-button.js";
import "@material/web/button/outlined-button.js";
import "@material/web/labs/card/filled-card.js";

import { type FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../AuthContext";

function errorMessage(e: unknown): string {
  if (e && typeof e === "object" && "code" in e) return String((e as { code: unknown }).code);
  return String(e);
}

export function LoginPage() {
  const { user, loading, signInWithGoogle, signInWithFacebook, signInWithApple, signInWithEmail, signUpWithEmail } =
    useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!loading && user) return <Navigate to="/" replace />;

  async function withBusy(fn: () => Promise<void>) {
    setError(null);
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function handleEmailSubmit(e: FormEvent) {
    e.preventDefault();
    withBusy(() => (mode === "signin" ? signInWithEmail(email, password) : signUpWithEmail(email, password)));
  }

  return (
    <div style={{ display: "flex", justifyContent: "center", padding: "3rem 1rem" }}>
      <md-filled-card style={{ width: "100%", maxWidth: "26rem" }}>
        <div style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <h1 style={{ margin: 0, fontSize: "1.3rem", textAlign: "center" }}>AliExpress Product Research</h1>
          <p style={{ margin: 0, textAlign: "center", color: "var(--md-sys-color-on-surface-variant)" }}>
            Sign in to continue.
          </p>

          {error && <div style={{ color: "var(--md-sys-color-error)", fontSize: "0.85rem" }}>{error}</div>}

          <form onSubmit={handleEmailSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <md-outlined-text-field
              label="Email"
              type="email"
              value={email}
              oninput={(e: Event) => setEmail((e.target as HTMLInputElement).value)}
              required
            />
            <md-outlined-text-field
              label="Password"
              type="password"
              value={password}
              oninput={(e: Event) => setPassword((e.target as HTMLInputElement).value)}
              required
            />
            <md-filled-button type="submit" disabled={busy}>
              {mode === "signin" ? "Sign in" : "Create account"}
            </md-filled-button>
          </form>

          <button
            type="button"
            onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
            style={{
              background: "none",
              border: "none",
              color: "var(--md-sys-color-primary)",
              cursor: "pointer",
              font: "inherit",
              fontSize: "0.85rem",
            }}
          >
            {mode === "signin" ? "Need an account? Sign up" : "Already have an account? Sign in"}
          </button>

          <hr style={{ width: "100%", border: "none", borderTop: "1px solid var(--md-sys-color-outline-variant)" }} />

          <md-outlined-button type="button" disabled={busy} onClick={() => withBusy(signInWithGoogle)}>
            Continue with Google
          </md-outlined-button>
          <md-outlined-button type="button" disabled={busy} onClick={() => withBusy(signInWithFacebook)}>
            Continue with Facebook
          </md-outlined-button>
          <md-outlined-button type="button" disabled={busy} onClick={() => withBusy(signInWithApple)}>
            Continue with Apple
          </md-outlined-button>
        </div>
      </md-filled-card>
    </div>
  );
}
