// Talks directly to aliexpress_dashboard/api/app.py -- same endpoints
// dashboard/api_client.py calls, just fetch/TS instead of httpx/Python.
// The API key here is a build-time env var baked into the JS bundle:
// fine for this local-only test hitting a local/fixture-mode API, never
// something to ship like this to a real deployment (see README).
import type {
  FilterOptions,
  MomentumRow,
  Product,
  ProductFilters,
  ShortlistSummary,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL as string;
const API_KEY = import.meta.env.VITE_API_KEY as string;

async function fetchOnce(path: string, options: RequestInit): Promise<Response> {
  return fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "X-API-Key": API_KEY,
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
};
