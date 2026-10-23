export type User = {
  id: number;
  email: string;
  full_name: string;
  role: "operator" | "qa";
};
export type AuthReply = {
  access_token: string;
  token_type: "bearer";
  user: User;
};
const TOKEN_KEY = "ricegrade-prototype-session";
export const getToken = () => sessionStorage.getItem(TOKEN_KEY);
export const saveToken = (token: string) =>
  sessionStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => sessionStorage.removeItem(TOKEN_KEY);

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
  token: string | null = getToken(),
): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  )
    headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    let reason = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as {
        detail?: string | Array<{ msg?: string }>;
      };
      if (typeof payload.detail === "string") reason = payload.detail;
      else if (Array.isArray(payload.detail))
        reason = payload.detail
          .map((item) => item.msg || "Invalid input")
          .join("; ");
    } catch {
      /* a non-JSON error response */
    }
    throw new Error(reason);
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

export async function getProtectedImage(id: number): Promise<string> {
  const response = await fetch(`/api/evaluations/${id}/image`, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    cache: "no-store",
  });
  if (!response.ok) throw new Error("Unable to load assessment image");
  return URL.createObjectURL(await response.blob());
}
