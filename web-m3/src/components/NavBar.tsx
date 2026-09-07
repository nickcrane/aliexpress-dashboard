import "@material/web/button/text-button.js";

import type { CSSProperties } from "react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../AuthContext";

export function NavBar() {
  const { user, signOut } = useAuth();

  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        gap: "1.5rem",
        padding: "0.75rem 1rem",
        background: "var(--md-sys-color-surface-container)",
        borderBottom: "1px solid var(--md-sys-color-outline-variant)",
        flexWrap: "wrap",
      }}
    >
      <strong style={{ fontSize: "1.1rem" }}>AliExpress Product Research</strong>
      <nav style={{ display: "flex", gap: "1rem" }}>
        <NavLink to="/" end style={navStyle}>
          Products
        </NavLink>
        <NavLink to="/momentum" style={navStyle}>
          Momentum
        </NavLink>
        <NavLink to="/shortlists" style={navStyle}>
          Shortlists
        </NavLink>
      </nav>
      {user && (
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <span style={{ fontSize: "0.85rem", color: "var(--md-sys-color-on-surface-variant)" }}>
            Signed in as {user.email ?? user.displayName ?? user.uid}
          </span>
          <md-text-button type="button" onClick={() => signOut()}>
            Sign out
          </md-text-button>
        </div>
      )}
    </header>
  );
}

function navStyle({ isActive }: { isActive: boolean }): CSSProperties {
  return {
    textDecoration: "none",
    color: isActive ? "var(--md-sys-color-primary)" : "var(--md-sys-color-on-surface)",
    fontWeight: isActive ? 600 : 400,
  };
}
