import { createRoot } from "react-dom/client";

import "./theme.css";
import App from "./App.tsx";

// No StrictMode: its dev-only double-effect-invocation raced with the CORS
// preflight on a hard page load, intermittently surfacing a misleading
// "Failed to fetch" error even though the actual request succeeded (the
// underlying data flow was confirmed correct via direct curl and a manual
// fetch() from devtools -- this was specifically about the double-mount,
// not a real bug). StrictMode's double-invoke is stripped in production
// builds anyway; fine to skip for this local visual test.
createRoot(document.getElementById("root")!).render(<App />);
