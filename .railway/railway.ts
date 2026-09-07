import { defineRailway, github, image, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const aliexpressDashboardVolume = volume("aliexpress-dashboard-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "us-west2", sizeMB: 5000 });
  const aliexpressDashboard = service("aliexpress-dashboard", {
    source: github("nickcrane/aliexpress-dashboard", { upstreamUrl: "https://github.com/nickcrane/aliexpress-dashboard" }),
    replicas: { "us-west2": 1 },
    volumeMounts: { "/data": aliexpressDashboardVolume },
    env: { AE_API_KEY: preserve(), AE_APP_KEY: preserve(), AE_APP_SECRET: preserve(), AE_BACKOFF_BASE_SECONDS: preserve(), AE_BACKOFF_MAX_SECONDS: preserve(), AE_CALLBACK_URL: preserve(), AE_DB_PATH: preserve(), AE_FIXTURES_DIR: preserve(), AE_MAX_RETRIES: preserve(), AE_MIN_REQUEST_INTERVAL_SECONDS: preserve(), AE_MODE: preserve(), AE_SHIP_TO_COUNTRY: preserve(), AE_TARGET_CURRENCY: preserve(), AE_TARGET_LANGUAGE: preserve(), AE_TOKEN_PATH: preserve(), AE_TOKEN_SEED: preserve(), AE_TRACKING_ID: preserve() },
  });
  const curl = service("curl", {
    source: image("curlimages/curl:latest"),
    start: "sh -c 'curl -s -w \"\\nHTTP_STATUS:%{http_code}\\n\" -X POST -H \"X-API-Key: $AE_API_KEY\" https://aliexpress-dashboard-production.up.railway.app/refresh-token'",
    replicas: { "us-west2": 1 },
    deploy: { cronSchedule: "0 */6 * * *", restartPolicyType: "NEVER" },
    env: { AE_API_KEY: preserve() },
  });
  const aliexpressDashboardUi = service("aliexpress-dashboard-ui", {
    // Was the Bootstrap web app (web/app.py); now builds+serves the M3 SPA
    // and its /api/* auth proxy (spa/app.py) via Dockerfile.spa instead --
    // see that file and web-m3/README.md. Same domain, same allowlist.
    source: github("nickcrane/aliexpress-dashboard"),
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile.spa" },
    replicas: { "us-west2": 1 },
    env: {
      AE_API_BASE_URL: preserve(),
      AE_API_KEY: preserve(),
      AE_AUTH_COOKIE_SECRET: preserve(),
      AE_AUTH_REDIRECT_URI: preserve(),
      AE_DASHBOARD_ALLOWED_EMAILS: preserve(),
      AE_FIREBASE_PROJECT_ID: "aliexpressproductdashboard",
      AE_GOOGLE_CLIENT_ID: preserve(),
      AE_GOOGLE_CLIENT_SECRET: preserve(),
      AE_MODE: preserve(),
      AE_WEB_REDIRECT_URI: preserve(),
      AE_WEB_SESSION_SECRET: preserve(),
    },
  });
  const aliexpressCollectorCron = service("aliexpress-collector-cron", {
    source: image("curlimages/curl:latest"),
    start: "sh -c 'curl -sf -X POST -H \"X-API-Key: $AE_API_KEY\" https://aliexpress-dashboard-production.up.railway.app/collect'",
    replicas: { "us-west2": 1 },
    deploy: { cronSchedule: "0 6 * * *", restartPolicyType: "NEVER" },
    env: { AE_API_KEY: preserve() },
  });

  return project("zestful-cooperation", {
    resources: [aliexpressDashboard, curl, aliexpressDashboardUi, aliexpressCollectorCron, aliexpressDashboardVolume],
  });
});
