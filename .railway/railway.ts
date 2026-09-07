import { defineRailway, github, image, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const aliexpressDashboardVolume = volume("aliexpress-dashboard-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "us-west2", sizeMB: 5000 });
  const aliexpressDashboard = service("aliexpress-dashboard", {
    source: github("nickcrane/aliexpress-dashboard", { upstreamUrl: "https://github.com/nickcrane/aliexpress-dashboard" }),
    replicas: { "us-west2": 1 },
    volumeMounts: { "/data": aliexpressDashboardVolume },
    env: { AE_API_KEY: preserve(), AE_APP_KEY: preserve(), AE_APP_SECRET: preserve(), AE_BACKOFF_BASE_SECONDS: preserve(), AE_BACKOFF_MAX_SECONDS: preserve(), AE_CALLBACK_URL: preserve(), AE_DB_PATH: preserve(), AE_FIXTURES_DIR: preserve(), AE_MAX_RETRIES: preserve(), AE_MIN_REQUEST_INTERVAL_SECONDS: preserve(), AE_MODE: preserve(), AE_SHIP_TO_COUNTRY: preserve(), AE_TARGET_CURRENCY: preserve(), AE_TARGET_LANGUAGE: preserve(), AE_TOKEN_PATH: preserve(), AE_TOKEN_SEED: preserve(), AE_TRACKING_ID: preserve() },
  });
  const aliexpressApiTokenRefreshCron = service("aliexpress-api-token-refresh-cron", {
    // -f: confirmed live this was silently swallowing failures -- without
    // it, curl exits 0 on a 502 same as on a 200, so a dead refresh
    // token showed as "Completed" in Railway with nothing to notice it
    // by. With -f, a failed refresh now surfaces as Crashed, matching
    // the other two curl-image crons below.
    source: image("curlimages/curl:latest"),
    start: "sh -c 'curl -sf -X POST -H \"X-API-Key: $AE_API_KEY\" https://aliexpress-dashboard-production.up.railway.app/refresh-token'",
    replicas: { "us-west2": 1 },
    deploy: { cronSchedule: "0 */6 * * *", restartPolicyType: "NEVER" },
    networking: { privateNetworkEndpoint: "curl" },
    env: { AE_API_KEY: preserve() },
  });
  const aliexpressDashboardUi = service("aliexpress-dashboard-ui", {
    source: github("nickcrane/aliexpress-dashboard"),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile.spa" },
    replicas: { "us-west2": 1 },
    env: {
      AE_API_BASE_URL: preserve(),
      AE_API_KEY: preserve(),
      AE_DASHBOARD_ALLOWED_EMAILS: preserve(),
      AE_FIREBASE_PROJECT_ID: preserve(),
      AE_GOOGLE_CLIENT_ID: preserve(),
      AE_GOOGLE_CLIENT_SECRET: preserve(),
      AE_MODE: preserve(),
      AE_WEB_REDIRECT_URI: preserve(),
      AE_WEB_SESSION_SECRET: preserve(),
      // Consumed at Docker build time (Dockerfile.spa passes these through
      // as build args) to bake Vite's client-side Firebase config into the
      // bundle. Already set directly on the Railway service -- preserve()
      // rather than a literal here, so this file (committed to a public
      // repo) doesn't itself become the thing search/scanning tools flag,
      // even though Firebase's own model treats this object as safe to
      // ship in a public browser bundle (unlike AE_API_KEY etc. above).
      VITE_FIREBASE_API_KEY: preserve(),
      VITE_FIREBASE_AUTH_DOMAIN: preserve(),
      VITE_FIREBASE_PROJECT_ID: preserve(),
      VITE_FIREBASE_APP_ID: preserve(),
    },
  });
  const aliexpressCollectorCron = service("aliexpress-collector-cron", {
    source: image("curlimages/curl:latest"),
    start: "sh -c 'curl -sf -X POST -H \"X-API-Key: $AE_API_KEY\" https://aliexpress-dashboard-production.up.railway.app/collect'",
    replicas: { "us-west2": 1 },
    deploy: { cronSchedule: "0 6 * * *", restartPolicyType: "NEVER" },
    env: { AE_API_KEY: preserve() },
  });
  const aliexpressCategorySyncCron = service("aliexpress-category-sync-cron", {
    // Categories change far less often than products, so this runs weekly
    // rather than sharing the daily collector schedule -- see
    // aliexpress_dashboard/collector/runner.py:sync_categories.
    source: image("curlimages/curl:latest"),
    start: "sh -c 'curl -sf -X POST -H \"X-API-Key: $AE_API_KEY\" https://aliexpress-dashboard-production.up.railway.app/sync-categories'",
    replicas: { "us-west2": 1 },
    deploy: { cronSchedule: "0 4 * * 1", restartPolicyType: "NEVER" },
    // References the dashboard service's own AE_API_KEY rather than a
    // literal or a second preserve() slot, so this key exists in exactly
    // one place instead of needing to be kept in sync across services.
    env: { AE_API_KEY: aliexpressDashboard.env.AE_API_KEY },
  });

  return project("zestful-cooperation", {
    resources: [
      aliexpressDashboard,
      aliexpressApiTokenRefreshCron,
      aliexpressDashboardUi,
      aliexpressCollectorCron,
      aliexpressCategorySyncCron,
      aliexpressDashboardVolume,
    ],
  });
});
