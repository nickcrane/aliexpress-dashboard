# Web UI (Material 3)

The live dashboard UI, built with Google's official Material 3 web
components (`@material/web`) -- same three pages (Products, Momentum,
Shortlists) as the earlier Bootstrap web app (`aliexpress_dashboard/web/`),
same backend API, different presentation layer. Replaced the Bootstrap app
as the deployed UI; see [Why Material Web, not MUI](#why-material-web-not-mui)
for why this component set specifically.

Gated behind real sign-in (email/password, Google, Facebook, Apple) via
Firebase Authentication -- see [Auth setup](#auth-setup-firebase) below.
Login only proves *who* someone is; `aliexpress_dashboard/spa/security.py`
then checks that email against the same `AE_DASHBOARD_ALLOWED_EMAILS`
allowlist the Bootstrap app used, so signing in isn't enough on its own.

The AliExpress API key never reaches the browser: this app doesn't call
`aliexpress_dashboard/api/` directly. It calls `/api/*` on
`aliexpress_dashboard/spa/app.py` instead, which verifies the caller's
Firebase token + allowlist membership and only then forwards the request
to the real API with `AE_API_KEY` attached server-side. In production
that proxy and this app's built static files are served from the same
Dockerfile.spa image/service, so there's no cross-origin call at all.

## Run it locally

Three processes -- this mirrors production (SPA -> proxy -> API) rather
than talking to the API directly, so the allowlist/auth path is actually
exercised in dev too:

```bash
# 1. The data API
AE_MODE=fixture uvicorn aliexpress_dashboard.api.app:app --port 8000

# 2. The auth proxy in front of it
AE_API_BASE_URL=http://localhost:8000 AE_API_KEY=<matches AE_API_KEY below> \
  AE_FIREBASE_PROJECT_ID=<your-project-id> AE_DASHBOARD_ALLOWED_EMAILS=<your-email> \
  uvicorn aliexpress_dashboard.spa.app:app --port 8503

# 3. The SPA itself
cd web-m3
npm install
cp .env.local.example .env.local   # fill in the Firebase config below
npm run dev
```

`vite.config.ts`'s dev server proxies `/api/*` to `localhost:8503`, so
`web-m3`'s own `VITE_API_BASE_URL` can stay unset (it only matters if
you want to point dev at something other than that local proxy).

`AE_API_KEY` needs to match between processes 1 and 2 -- process 1 checks
incoming requests against it (`api/security.py`), process 2 attaches it
to outgoing ones. Any value works locally as long as it's the same on
both sides.

## Auth setup (Firebase)

Firebase Authentication, not a hand-rolled backend -- one SDK covers all
four sign-in methods instead of building a real auth service plus email/
SMS sending infrastructure from scratch. Phone sign-in was deliberately
left out of this pass (real SMS costs money per message and needs a live
test number); the other four are wired up.

**One unavoidable real-world cost**: Apple requires a paid Apple Developer
Program membership ($99/year) to configure Sign in with Apple, regardless
of using Firebase or hand-rolling it.

1. **Firebase Console** (console.firebase.google.com) -> create a project
   -> Build -> Authentication -> get started.
2. **Sign-in methods** to enable, under Authentication -> Sign-in method:
   - **Email/Password** -- one toggle, no external app registration.
   - **Google** -- also near-automatic; Firebase provisions its own OAuth
     client for this.
   - **Facebook** -- needs an app at developers.facebook.com (add the
     "Facebook Login" product), which gives you an App ID + App Secret to
     paste into Firebase's Facebook provider config. Firebase in turn
     gives you an OAuth redirect URI to paste into the Facebook app's
     Valid OAuth Redirect URIs, and the Facebook app's own **App Domains**
     setting needs Firebase's `*.firebaseapp.com` domain (not your actual
     site) -- Facebook only ever redirects back to Firebase's hosted
     handler.
   - **Apple** -- needs a Services ID configured for Sign in with Apple
     under your paid Apple Developer account, plus a private key/Team ID/
     Key ID, all pasted into Firebase's Apple provider config.
3. **Authorized domains** (Authentication -> Settings): add the Railway
   domain this deploys to (e.g. `aliexpress-dashboard-ui-production.up.railway.app`)
   alongside the `localhost` entry Firebase includes by default.
4. **Project Settings -> General -> Your apps** -> add a Web app (the
   `</>` icon) -> copy the small config object it shows you
   (`apiKey`, `authDomain`, `projectId`, `appId`) into `.env.local`'s
   `VITE_FIREBASE_*` variables (local dev) and the matching `VITE_FIREBASE_*`
   / `AE_FIREBASE_PROJECT_ID` build/runtime variables on Railway.

Email/password can be fully tested with just step 1-2's Email/Password
toggle -- no Facebook/Apple app registration needed to try that one.
Google, Facebook, and Apple each need their own real credentials before a
sign-in attempt will actually complete; until then their buttons still
render and open a real provider sign-in popup (or a clear Firebase
configuration error if that provider isn't enabled yet).

Whoever signs in also needs to be on `AE_DASHBOARD_ALLOWED_EMAILS` (set on
the `aliexpress-dashboard-ui` Railway service) -- Firebase proves identity,
that env var decides access.

## Deploying

Built and served by `Dockerfile.spa` at the repo root (multi-stage: Node
to build this app, Python to serve `dist/` + run the `/api/*` proxy) --
see that file. Railway's `aliexpress-dashboard-ui` service is pointed at
it; `railway config apply` from `.railway/railway.ts` manages that service
definition.

## Why Material Web, not MUI

MUI's core components are still primarily Material 2 under the hood;
Material Web (`@material/web`) is Google's own official Material 3
implementation, used here directly as custom elements
(`<md-filled-button>`, etc.) rather than through a component library with
its own theming layer in between.

One component used here (`labs/card`) is in Material Web's `labs/`
namespace, meaning its API isn't finalized yet -- worth knowing before
relying on it longer-term. The responsive filter panel is hand-built with
plain CSS rather than a Material Web drawer component, since the stable
catalog doesn't ship one yet.
