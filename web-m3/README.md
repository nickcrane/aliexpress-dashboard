# M3 test build

A local-only experiment comparing Google's official Material 3 web
components (`@material/web`) against the Bootstrap web app
(`aliexpress_dashboard/web/`) -- same three pages (Products, Momentum,
Shortlists), same backend API, different presentation layer. Not
deployed, not production code.

Gated behind real sign-in (email/password, Google, Facebook, Apple) via
Firebase Authentication -- see [Auth setup](#auth-setup-firebase) below.
This is authentication only (proving who someone is), not authorization:
anyone who successfully signs in via any of the four methods gets in,
unlike the Bootstrap app's email allowlist.

## Run it

```bash
npm install
cp .env.local.example .env.local   # then fill in the Firebase config below,
                                    # and edit VITE_API_BASE_URL if your API runs elsewhere
npm run dev
```

Needs the backend API running with CORS opened up for Vite's dev origin:

```bash
AE_CORS_ALLOWED_ORIGINS=http://localhost:5173 uvicorn aliexpress_dashboard.api.app:app --port 8000
```

`AE_CORS_ALLOWED_ORIGINS` is empty by default everywhere else (including
the deployed Railway backend) -- this doesn't change anything unless you
set it.

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
     Valid OAuth Redirect URIs.
   - **Apple** -- needs a Services ID configured for Sign in with Apple
     under your paid Apple Developer account, plus a private key/Team ID/
     Key ID, all pasted into Firebase's Apple provider config.
3. **Authorized domains** (Authentication -> Settings): `localhost` is
   included by default, so local dev needs nothing extra here; add your
   real domain later if this gets deployed anywhere.
4. **Project Settings -> General -> Your apps** -> add a Web app (the
   `</>` icon) -> copy the small config object it shows you
   (`apiKey`, `authDomain`, `projectId`, `appId`) into `.env.local`'s
   `VITE_FIREBASE_*` variables.

Email/password can be fully tested with just step 1-2's Email/Password
toggle -- no Facebook/Apple app registration needed to try that one.
Google, Facebook, and Apple each need their own real credentials before a
sign-in attempt will actually complete; until then their buttons still
render and open a real provider sign-in popup (or a clear Firebase
configuration error if that provider isn't enabled yet).

## Why Material Web, not MUI

MUI's core components are still primarily Material 2 under the hood;
Material Web (`@material/web`) is Google's own official Material 3
implementation, used here directly as custom elements
(`<md-filled-button>`, etc.) rather than through a component library with
its own theming layer in between.

One component used here (`labs/card`) is in Material Web's `labs/`
namespace, meaning its API isn't finalized yet -- fine for a test, worth
knowing before relying on it longer-term. The responsive filter panel is
hand-built with plain CSS rather than a Material Web drawer component,
since the stable catalog doesn't ship one yet.
