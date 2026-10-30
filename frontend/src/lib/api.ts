type ApiErrorPayload = {
  detail?: unknown;
  message?: unknown;
  [key: string]: unknown;
};

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ApiOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
};

type PaginatedResponse<T> = {
  next: string | null;
  results: T[];
};

const API_BASE_URL = (
  import.meta.env["VITE_API_BASE_URL"] || "http://127.0.0.1:8000/api/v1"
).replace(/\/+$/, "");
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);
let csrfToken: string | null = null;
let csrfRequest: Promise<string> | null = null;

function describeError(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") return fallback;
  const value = payload as ApiErrorPayload;
  if (typeof value.detail === "string") return value.detail;
  if (typeof value.message === "string") return value.message;

  const messages = Object.entries(value).flatMap(([field, errors]) => {
    if (typeof errors === "string") return [`${field}: ${errors}`];
    if (Array.isArray(errors)) return errors.map((error) => `${field}: ${String(error)}`);
    return [];
  });
  return messages.length ? messages.join(" ") : fallback;
}

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    throw new ApiError(
      describeError(payload, `La requête a échoué (${response.status}).`),
      response.status,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function getCsrfToken(): Promise<string> {
  if (csrfToken) return csrfToken;
  if (!csrfRequest) {
    csrfRequest = fetch(`${API_BASE_URL}/users/csrf/`, {
      credentials: "include",
      headers: { Accept: "application/json" },
    })
      .then(async (response) => {
        const payload = await readResponse<{ csrfToken: string }>(response);
        csrfToken = payload.csrfToken;
        return csrfToken;
      })
      .finally(() => {
        csrfRequest = null;
      });
  }
  return csrfRequest;
}

function isFormDataBody(body: unknown): body is FormData {
  return typeof FormData !== "undefined" && body instanceof FormData;
}

async function send<T>(url: string, options: ApiOptions = {}): Promise<T> {
  const { body, ...requestOptions } = options;
  const method = (requestOptions.method ?? "GET").toUpperCase();
  const headers = new Headers(requestOptions.headers);
  const isMultipart = isFormDataBody(body);
  headers.set("Accept", "application/json");

  if (body !== undefined && !isMultipart) headers.set("Content-Type", "application/json");
  if (UNSAFE_METHODS.has(method)) headers.set("X-CSRFToken", await getCsrfToken());

  const request: RequestInit = {
    ...requestOptions,
    method,
    credentials: "include",
    headers,
    ...(body === undefined ? {} : { body: isMultipart ? body : JSON.stringify(body) }),
  };
  const response = await fetch(url, request);
  return readResponse<T>(response);
}

function endpoint(path: string, params?: Record<string, string | number | boolean | undefined>) {
  const url = new URL(`${API_BASE_URL}/${path.replace(/^\/+/, "")}`);
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined) url.searchParams.set(key, String(value));
  }
  return url;
}

export const api = {
  get<T>(path: string, params?: Record<string, string | number | boolean | undefined>) {
    return send<T>(endpoint(path, params).toString());
  },

  post<T>(path: string, body?: unknown, headers?: HeadersInit) {
    return send<T>(endpoint(path).toString(), {
      method: "POST",
      body,
      ...(headers === undefined ? {} : { headers }),
    }).then((result) => {
      const normalizedPath = path.replace(/^\/+|\/+$/g, "");
      if (normalizedPath === "users/login" || normalizedPath === "users/logout") {
        csrfToken = null;
      }
      return result;
    });
  },

  patch<T>(path: string, body: unknown) {
    return send<T>(endpoint(path).toString(), { method: "PATCH", body });
  },

  async download(path: string, filename: string) {
    const response = await fetch(endpoint(path).toString(), {
      credentials: "include",
      headers: { Accept: "application/octet-stream" },
    });
    if (!response.ok) await readResponse<void>(response);
    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
  },

  async blob(path: string, accept = "application/pdf") {
    const response = await fetch(endpoint(path).toString(), {
      credentials: "include",
      headers: { Accept: accept },
    });
    if (!response.ok) await readResponse<void>(response);
    return response.blob();
  },

  put<T>(path: string, body: unknown) {
    return send<T>(endpoint(path).toString(), { method: "PUT", body });
  },

  delete<T>(path: string) {
    return send<T>(endpoint(path).toString(), { method: "DELETE" });
  },

  async list<T>(
    path: string,
    params?: Record<string, string | number | boolean | undefined>,
  ): Promise<T[]> {
    const firstUrl = endpoint(path, { ...params, page: 1, page_size: 100 });
    const all: T[] = [];
    let url: URL | null = firstUrl;

    while (url) {
      const page: PaginatedResponse<T> | T[] = await send<PaginatedResponse<T> | T[]>(
        url.toString(),
      );
      if (Array.isArray(page)) {
        all.push(...page);
        url = null;
      } else {
        all.push(...page.results);
        url = page.next ? new URL(page.next) : null;
      }
    }

    return all;
  },
};
