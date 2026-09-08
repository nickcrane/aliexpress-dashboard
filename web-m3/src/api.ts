// Talks to aliexpress_dashboard/spa/app.py's /api/* proxy, which forwards
// to aliexpress_dashboard/api/app.py with the AliExpress API key attached
// server-side -- the key never reaches this bundle. Each request instead
// carries the signed-in user's Firebase ID token; the proxy verifies it
// and checks the same email allowlist the Bootstrap app uses. Defaults to
// a same-origin relative path since the SPA and its proxy are served from
// the same service in production; vite.config.ts forwards that path to a
// local proxy instance in dev (see web-m3/README.md).
import type {
  BusinessProfile,
  FilterOptions,
  MomentumRow,
  Product,
  ProductFilters,
  ShortlistSummary,
} from "./types";
import { auth } from "./firebase";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || "/api";

async function fetchOnce(path: string, options: RequestInit): Promise<Response> {
  const token = await auth?.currentUser?.getIdToken();
  return fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
}

const RETRY_DELAYS_MS = [100, 250, 500, 1000, 1500];

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  // The very first cross-origin request right after a fresh page load can
  // throw a plain "Failed to fetch" (confirmed live: a manual fetch from
  // the same page moments later succeeds instantly with the exact same
  // URL/headers -- a timing race in how soon after navigation the browser
  // is ready for a new cross-origin connection, not a real app/CORS bug).
  // Retrying with backoff papers over it cheaply; a normal request that
  // isn't racing anything just succeeds on the first attempt as before.
  let response: Response | undefined;
  let lastError: unknown;
  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
    try {
      response = await fetchOnce(path, options);
      break;
    } catch (e) {
      lastError = e;
      if (attempt < RETRY_DELAYS_MS.length) {
        await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[attempt]));
      }
    }
  }
  if (!response) throw lastError;
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${options.method ?? "GET"} ${path} -> ${response.status}: ${body}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function filterParams(filters: ProductFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  }
  return params.toString();
}

export const api = {
  loadCurrentProducts: (filters: ProductFilters) =>
    request<Product[]>(`/products?${filterParams(filters)}`),

  getFilters: () => request<FilterOptions>("/filters"),

  maxTargetPrice: (currency: string) =>
    request<{ max_price: number | null }>(`/filters/max-price?currency=${encodeURIComponent(currency)}`).then(
      (r) => r.max_price,
    ),

  getMomentum: (productIds: number[], windowDays: number) => {
    if (productIds.length === 0) return Promise.resolve<MomentumRow[]>([]);
    return request<MomentumRow[]>(
      `/momentum?product_ids=${productIds.join(",")}&window_days=${windowDays}`,
    );
  },

  listShortlists: () => request<ShortlistSummary[]>("/shortlists"),

  loadShortlistProducts: (shortlistId: number) =>
    request<Product[]>(`/shortlists/${shortlistId}/products`),

  saveShortlist: (name: string, productIds: number[]) =>
    request<{ id: number; name: string }>("/shortlists", {
      method: "POST",
      body: JSON.stringify({ name, product_ids: productIds }),
    }),

  removeProductFromShortlist: (shortlistId: number, productId: number) =>
    request<{ status: string }>(`/shortlists/${shortlistId}/products/${productId}`, {
      method: "DELETE",
    }),

  deleteShortlist: (shortlistId: number) =>
    request<{ status: string }>(`/shortlists/${shortlistId}`, { method: "DELETE" }),

  getBusinessProfile: async (): Promise<BusinessProfile | null> => {
    // Not a shared `request()` call: no business profile yet is a normal
    // state (every new user starts here), not an error to throw on.
    const response = await fetchOnce("/business-profile", {});
    if (response.status === 404) return null;
    if (!response.ok) {
      throw new Error(`GET /business-profile -> ${response.status}: ${await response.text()}`);
    }
    return response.json();
  },

  synthesizeOnboarding: (answers: Record<string, string>) =>
    request<BusinessProfile>("/onboarding/synthesize", {
      method: "POST",
      body: JSON.stringify({ answers }),
    }),
};
