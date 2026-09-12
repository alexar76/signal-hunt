import type { Evidence, HeroEvent, LeaderboardEntry, PlayerProfile, Round, Verdict } from './types';

const TOKEN_KEY = 'signal-hunt-session';

type Session = { id: string; handle: string; token: string; public_profile: boolean };

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(path, { ...init, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    const message = Array.isArray(detail)
      ? detail.map((item: { msg?: string } | string) => (
        typeof item === 'string' ? item : (item?.msg || JSON.stringify(item))
      )).join('; ')
      : (typeof detail === 'string' ? detail : (body.error || `HTTP ${response.status}`));
    throw new ApiError(message, response.status);
  }
  return body as T;
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export async function ensureSession(): Promise<Session> {
  const saved = localStorage.getItem(TOKEN_KEY);
  if (saved) {
    try {
      return JSON.parse(saved) as Session;
    } catch {
      localStorage.removeItem(TOKEN_KEY);
    }
  }
  const session = await request<Session>('/api/v1/session', {
    method: 'POST',
    body: JSON.stringify({}),
  });
  localStorage.setItem(TOKEN_KEY, JSON.stringify(session));
  return session;
}

export const api = {
  live: (token: string) => request<Round>('/api/v1/rounds/live', {}, token),
  evidence: (token: string, roundId: string, evidenceId: string) =>
    request<Evidence>(`/api/v1/rounds/${roundId}/evidence/${evidenceId}`, { method: 'POST' }, token),
  submit: (
    token: string,
    roundId: string,
    answer_code: string,
    confidence: number,
    follow_up_answer?: string | null,
  ) =>
    request<Verdict>(`/api/v1/rounds/${roundId}/submit`, {
      method: 'POST',
      body: JSON.stringify({
        answer_code,
        confidence,
        ...(follow_up_answer ? { follow_up_answer } : {}),
      }),
    }, token),
  broadcast: (token: string, roundId: string) =>
    request<{ ok: boolean; already: boolean; event: HeroEvent | null }>(
      `/api/v1/rounds/${roundId}/broadcast`,
      { method: 'POST' },
      token,
    ),
  leaderboard: () => request<{ entries: LeaderboardEntry[] }>('/api/v1/leaderboard?limit=12'),
  weeklyLeaderboard: () =>
    request<{ week_id: string; entries: LeaderboardEntry[] }>('/api/v1/leaderboard/weekly?limit=12'),
  profile: (token: string) => request<PlayerProfile>('/api/v1/profile', {}, token),
  updateProfile: (token: string, handle: string, public_profile: boolean) =>
    request<PlayerProfile>('/api/v1/profile', {
      method: 'PUT',
      body: JSON.stringify({ handle, public_profile }),
    }, token),
  heroes: () => request<{
    payload: { events: HeroEvent[] };
    signature: { algorithm: string; public_key: string; value: string };
  }>('/api/v1/heroes/feed?limit=24'),
};
