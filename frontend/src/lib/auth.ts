// Auth utilities — token storage and user state

export const TOKEN_KEY = "tap_token";
export const REFRESH_KEY = "tap_refresh";
export const USER_KEY = "tap_user";

export interface AuthUser {
  user_id: number;
  email: string;
  full_name: string | null;
  is_admin?: boolean;
  email_verified?: boolean;
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function saveTokens(accessToken: string, refreshToken?: string | null): void {
  localStorage.setItem(TOKEN_KEY, accessToken);
  if (refreshToken) {
    localStorage.setItem(REFRESH_KEY, refreshToken);
  }
}

export function getUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveAuth(token: string, user: AuthUser, refreshToken?: string | null): void {
  saveTokens(token, refreshToken);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function updateUser(patch: Partial<AuthUser>): void {
  const current = getUser();
  if (current) {
    localStorage.setItem(USER_KEY, JSON.stringify({ ...current, ...patch }));
  }
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}
