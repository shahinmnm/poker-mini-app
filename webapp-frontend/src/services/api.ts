import { GameState, GameListItem, AuthResponse, GameAction } from '../types/game.types';

type HeadersRecord = Record<string, string>;

interface ClientUserContext {
  id: number;
  username?: string | null;
  lang?: string | null;
}

const resolvePublicOrigin = (): string => {
  if (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_PUBLIC_ORIGIN) {
    return ((import.meta as any).env.VITE_PUBLIC_ORIGIN as string).replace(/\/$/, '');
  }
  if (typeof window !== 'undefined' && window.location?.origin) {
    return window.location.origin.replace(/\/$/, '');
  }
  return 'https://poker.shahin8n.sbs';
};

const PUBLIC_ORIGIN = resolvePublicOrigin();

const resolveApiBaseUrl = () => {
  if (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_API_URL) {
    return (import.meta as any).env.VITE_API_URL as string;
  }
  return `${PUBLIC_ORIGIN}/api`;
};

const API_BASE_URL = resolveApiBaseUrl();

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

class ExchangeUnavailableError extends Error {}
class ExchangeAuthError extends Error {}

let cachedInitData: string | null = null;
let cachedJwt: string | null = null;
let cachedUser: ClientUserContext | null = null;
let exchangeSupported: boolean | null = null;
let bootstrapPromise: Promise<void> | null = null;

const readTelegramInitData = (): string | null => {
  try {
    const tg = (window as any)?.Telegram?.WebApp;
    return tg?.initData || null;
  } catch {
    return null;
  }
};

const parseUserFromInitData = (initData: string | null): ClientUserContext | null => {
  if (!initData) return null;
  try {
    const params = new URLSearchParams(initData);
    const rawUser = params.get('user');
    if (!rawUser) return null;
    const user = JSON.parse(rawUser);
    if (!user?.id) return null;
    return {
      id: Number(user.id),
      username: user.username ?? null,
      lang: user.language_code ?? user.lang ?? null,
    };
  } catch {
    return null;
  }
};

const getAuthHeaders = (): HeadersRecord => {
  const headers: HeadersRecord = {};
  if (cachedJwt) {
    headers['Authorization'] = `Bearer ${cachedJwt}`;
  } else if (cachedInitData) {
    headers['X-Telegram-Init-Data'] = cachedInitData;
  }
  return headers;
};

const exchangeForJwt = async (initData: string): Promise<string> => {
  const response = await fetch(`${API_BASE_URL}/auth/exchange`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-Telegram-Init-Data': initData,
    },
    body: JSON.stringify({ initData }),
  });

  if (response.status === 404) {
    throw new ExchangeUnavailableError('exchange endpoint unavailable');
  }

  if (response.status === 401) {
    throw new ExchangeAuthError('initData rejected');
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new ApiError(response.status, payload.detail || 'Failed to exchange token');
  }

  const payload = await response.json();
  if (!payload?.token) {
    throw new ApiError(response.status, 'Invalid exchange response');
  }
  return payload.token as string;
};

const refreshAuth = async (force = false): Promise<boolean> => {
  const latestInitData = readTelegramInitData();
  const initDataChanged = latestInitData !== cachedInitData;
  if (!latestInitData) {
    cachedInitData = null;
    cachedJwt = null;
    cachedUser = null;
    return false;
  }

  if (!force && !initDataChanged && (cachedJwt || exchangeSupported === false)) {
    return false;
  }

  cachedInitData = latestInitData;
  cachedUser = parseUserFromInitData(latestInitData);

  if (exchangeSupported === false) {
    cachedJwt = null;
    return initDataChanged;
  }

  try {
    cachedJwt = await exchangeForJwt(latestInitData);
    exchangeSupported = true;
    return true;
  } catch (error) {
    if (error instanceof ExchangeUnavailableError) {
      exchangeSupported = false;
      cachedJwt = null;
      return initDataChanged;
    }
    if (error instanceof ExchangeAuthError) {
      cachedJwt = null;
      return initDataChanged;
    }
    throw error;
  }
};

export const bootstrapTelegramAuth = async (): Promise<void> => {
  if (!bootstrapPromise) {
    bootstrapPromise = refreshAuth(true).catch((error) => {
      console.warn('Failed to bootstrap Telegram auth:', error);
    }).finally(() => {
      bootstrapPromise = null;
    });
  }
  await bootstrapPromise;
};

export const getCachedTelegramUser = (): ClientUserContext | null => cachedUser;

async function fetchApi<T>(endpoint: string, options: RequestInit = {}, retry = true): Promise<T> {
  await bootstrapTelegramAuth();

  const headers = new Headers(options.headers || {});
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const authHeaders = getAuthHeaders();
  Object.entries(authHeaders).forEach(([key, value]) => {
    if (value) {
      headers.set(key, value);
    }
  });

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
    credentials: options.credentials ?? 'include',
  });

  if (response.status === 401 && retry) {
    await refreshAuth(true);
    return fetchApi<T>(endpoint, options, false);
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new ApiError(response.status, error.detail || 'Request failed');
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

// Auth endpoints
export const authenticateWithTelegram = async (initData: string): Promise<AuthResponse> => {
  return fetchApi<AuthResponse>('/auth/telegram', {
    method: 'POST',
    body: JSON.stringify({ initData }),
  });
};

// Game endpoints
export const getGameList = async (_token?: string): Promise<GameListItem[]> => {
  return fetchApi('/game/list');
};

export const getGameState = async (gameId: string, _token?: string): Promise<GameState> => {
  return fetchApi(`/game/state/${gameId}`);
};

export const joinGame = async (gameId: string, _token?: string): Promise<{ success: boolean }> => {
  return fetchApi(
    '/game/join',
    {
      method: 'POST',
      body: JSON.stringify({ game_id: gameId }),
    }
  );
};

export const performAction = async (action: GameAction, _token?: string): Promise<{ success: boolean }> => {
  return fetchApi(
    '/game/action',
    {
      method: 'POST',
      body: JSON.stringify(action),
    }
  );
};

export const leaveGame = async (gameId: string, _token?: string): Promise<{ success: boolean }> => {
  return fetchApi(
    '/game/leave',
    {
      method: 'POST',
      body: JSON.stringify({ game_id: gameId }),
    }
  );
};

interface CreateGameResponse {
  game_id: string;
  status: string;
}

export const createGame = async (
  stakeLevel: string,
  _token?: string,
  mode: string = 'private'
): Promise<CreateGameResponse> => {
  return fetchApi(
    '/game/create',
    {
      method: 'POST',
      body: JSON.stringify({ stake_level: stakeLevel, mode }),
    }
  );
};

// Group Game endpoints
export interface GroupGameInfo {
  game_id: string;
  chat_id: number;
  initiator_id: number;
  initiator_name: string;
  players: Array<{ id: number; name: string; joined_at: string }>;
  message_id: number | null;
  status: 'waiting' | 'starting' | 'active';
  created_at: string;
  min_players: number;
}

export interface ChatInfo {
  id: number;
  title: string;
  type: string;
}

export const startGroupGame = async (
  chatId: number,
  _token?: string,
  miniappUrl?: string
): Promise<GroupGameInfo> => {
  const result = await fetchApi<GroupGameInfo>(
    '/group-game/start',
    {
      method: 'POST',
      body: JSON.stringify({ chat_id: chatId, miniapp_url: miniappUrl }),
    }
  );
  // Ensure players is always an array
  if (result && !Array.isArray(result.players)) {
    result.players = [];
  }
  return result;
};

export const joinGroupGame = async (
  gameId: string,
  _token?: string,
  userName?: string
): Promise<GroupGameInfo> => {
  const result = await fetchApi<GroupGameInfo>(
    '/group-game/join',
    {
      method: 'POST',
      body: JSON.stringify({ game_id: gameId, user_name: userName }),
    }
  );
  // Ensure players is always an array
  if (result && !Array.isArray(result.players)) {
    result.players = [];
  }
  return result;
};

export const getGroupGame = async (
  gameId: string,
  _token?: string
): Promise<GroupGameInfo> => {
  const result = await fetchApi<GroupGameInfo>(`/group-game/${gameId}`);
  // Ensure players is always an array
  if (result && !Array.isArray(result.players)) {
    result.players = [];
  }
  return result;
};

export const listUserChats = async (_token?: string): Promise<ChatInfo[]> => {
  const result = await fetchApi<ChatInfo[]>('/group-game/chats/list');
  // Ensure we always return an array
  return Array.isArray(result) ? result : [];
};

export const sendMiniappToGroup = async (
  gameId: string,
  chatId: number,
  _token?: string,
  miniappUrl?: string
): Promise<{ success: boolean; message_id?: number }> => {
  return fetchApi<{ success: boolean; message_id?: number }>(
    `/group-game/${gameId}/send-miniapp?chat_id=${chatId}`,
    {
      method: 'POST',
      body: JSON.stringify({ miniapp_url: miniappUrl }),
    }
  );
};

// Tables endpoints
export interface TableDto {
  id: string;
  name: string;
  bb: number;
  max_players: number;
  seated: number;
  private: boolean;
  stakes?: string;
  players_count?: number;
  status?: string;
  is_private?: boolean;
}

export const apiTables = async (_token?: string): Promise<TableDto[]> => {
  const result = await fetchApi<TableDto[]>('/tables');
  // Ensure we always return an array
  return Array.isArray(result) ? result : [];
};

export const apiJoinTable = async (tableId: string, _token?: string): Promise<{ success: boolean; table_id: string }> => {
  return fetchApi<{ success: boolean; table_id: string }>(
    `/tables/${tableId}/join`,
    {
      method: 'POST',
    }
  );
};

// User stats and settings endpoints
interface BackendStats {
  hands_played: number;
  hands_won: number;
  total_profit: number;
  biggest_pot_won: number;
  avg_stake: number;
  current_streak: number;
  hand_distribution: Record<string, number>;
}

interface BackendSettings {
  fourColorDeck: boolean;
  showHandStrength: boolean;
  confirmAllIn: boolean;
  autoCheckFold: boolean;
  haptics: boolean;
  balance: number;
}

export interface UserStats {
  user_id: number;
  hands_played: number;
  biggest_win: number;
  biggest_loss: number;
  win_rate: number;
  last_played: string;
  streak_days: number;
  chip_balance: number;
  rank: string;
}

export interface UserSettings {
  user_id: number;
  theme: "auto" | "dark" | "light";
  notifications: boolean;
  locale: string;
  currency: string;
  experimental: boolean;
}

export const apiUserStats = async (_token?: string): Promise<UserStats> => {
  const [backendStats, backendSettings] = await Promise.all([
    fetchApi<BackendStats>('/user/stats'),
    fetchApi<BackendSettings>('/user/settings'),
  ]);
  
  // Transform backend response to match component expectations
  const winRate = backendStats.hands_played > 0 
    ? backendStats.hands_won / backendStats.hands_played 
    : 0;
  
  // Calculate rank based on hands played (simple ranking system)
  let rank = "Beginner";
  if (backendStats.hands_played >= 1000) rank = "Expert";
  else if (backendStats.hands_played >= 500) rank = "Advanced";
  else if (backendStats.hands_played >= 100) rank = "Intermediate";
  
  const userId = getCachedTelegramUser()?.id ?? 0;
  
  // Calculate biggest_loss from total_profit
  const biggestLoss = backendStats.total_profit < 0 
    ? Math.abs(backendStats.total_profit) 
    : 0;
  
  return {
    user_id: userId,
    hands_played: backendStats.hands_played,
    biggest_win: backendStats.biggest_pot_won,
    biggest_loss: biggestLoss,
    win_rate: winRate,
    last_played: new Date().toISOString(), // Backend doesn't provide this, using current date
    streak_days: backendStats.current_streak,
    chip_balance: backendSettings.balance,
    rank: rank,
  };
};

export const apiUserSettings = async (_token?: string): Promise<UserSettings> => {
  const backendSettings = await fetchApi<BackendSettings>('/user/settings');

  const userId = getCachedTelegramUser()?.id ?? 0;
  
  // Transform backend response to match component expectations
  // Backend doesn't have theme, notifications, locale, currency, experimental
  // So we'll use defaults or derive from available data
  return {
    user_id: userId,
    theme: "auto", // Default since backend doesn't provide this
    notifications: backendSettings.haptics, // Use haptics as proxy for notifications preference
    locale: "en", // Default
    currency: "USD", // Default
    experimental: backendSettings.autoCheckFold, // Use autoCheckFold as proxy for experimental features
  };
};