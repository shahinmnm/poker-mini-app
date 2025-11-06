import { GameState, GameListItem, AuthResponse, GameAction } from '../types/game.types';

// Get API base URL from environment or use default
const getApiBaseUrl = () => {
  if (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_API_URL) {
    return (import.meta as any).env.VITE_API_URL;
  }
  // Default to production API URL
  return 'https://poker.shahin8n.sbs/api';
};

const API_BASE_URL = getApiBaseUrl();

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  // Only add Authorization header if token is provided and not empty
  if (token && token.trim()) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new ApiError(response.status, error.detail || 'Request failed');
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
export const getGameList = async (token: string): Promise<GameListItem[]> => {
  return fetchApi('/game/list', {}, token);
};

export const getGameState = async (gameId: string, token: string): Promise<GameState> => {
  return fetchApi(`/game/state/${gameId}`, {}, token);
};

export const joinGame = async (gameId: string, token: string): Promise<{ success: boolean }> => {
  return fetchApi(
    '/game/join',
    {
      method: 'POST',
      body: JSON.stringify({ game_id: gameId }),
    },
    token
  );
};

export const performAction = async (action: GameAction, token: string): Promise<{ success: boolean }> => {
  return fetchApi(
    '/game/action',
    {
      method: 'POST',
      body: JSON.stringify(action),
    },
    token
  );
};

export const leaveGame = async (gameId: string, token: string): Promise<{ success: boolean }> => {
  return fetchApi(
    '/game/leave',
    {
      method: 'POST',
      body: JSON.stringify({ game_id: gameId }),
    },
    token
  );
};

interface CreateGameResponse {
  game_id: string;
  status: string;
}

export const createGame = async (
  stakeLevel: string,
  token: string,
  mode: string = 'private'
): Promise<CreateGameResponse> => {
  return fetchApi(
    '/game/create',
    {
      method: 'POST',
      body: JSON.stringify({ stake_level: stakeLevel, mode }),
    },
    token
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
  token: string,
  miniappUrl?: string
): Promise<GroupGameInfo> => {
  const result = await fetchApi<GroupGameInfo>(
    '/group-game/start',
    {
      method: 'POST',
      body: JSON.stringify({ chat_id: chatId, miniapp_url: miniappUrl }),
    },
    token
  );
  // Ensure players is always an array
  if (result && !Array.isArray(result.players)) {
    result.players = [];
  }
  return result;
};

export const joinGroupGame = async (
  gameId: string,
  token: string,
  userName?: string
): Promise<GroupGameInfo> => {
  const result = await fetchApi<GroupGameInfo>(
    '/group-game/join',
    {
      method: 'POST',
      body: JSON.stringify({ game_id: gameId, user_name: userName }),
    },
    token
  );
  // Ensure players is always an array
  if (result && !Array.isArray(result.players)) {
    result.players = [];
  }
  return result;
};

export const getGroupGame = async (
  gameId: string,
  token: string
): Promise<GroupGameInfo> => {
  const result = await fetchApi<GroupGameInfo>(`/group-game/${gameId}`, {}, token);
  // Ensure players is always an array
  if (result && !Array.isArray(result.players)) {
    result.players = [];
  }
  return result;
};

export const listUserChats = async (token: string): Promise<ChatInfo[]> => {
  const result = await fetchApi<ChatInfo[]>('/group-game/chats/list', {}, token);
  // Ensure we always return an array
  return Array.isArray(result) ? result : [];
};

export const sendMiniappToGroup = async (
  gameId: string,
  chatId: number,
  token: string,
  miniappUrl?: string
): Promise<{ success: boolean; message_id?: number }> => {
  return fetchApi<{ success: boolean; message_id?: number }>(
    `/group-game/${gameId}/send-miniapp?chat_id=${chatId}`,
    {
      method: 'POST',
      body: JSON.stringify({ miniapp_url: miniappUrl }),
    },
    token
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

export const apiTables = async (token?: string): Promise<TableDto[]> => {
  const result = await fetchApi<TableDto[]>('/tables', {}, token);
  // Ensure we always return an array
  return Array.isArray(result) ? result : [];
};

export const apiJoinTable = async (tableId: string, token?: string): Promise<{ success: boolean; table_id: string }> => {
  return fetchApi<{ success: boolean; table_id: string }>(
    `/tables/${tableId}/join`,
    {
      method: 'POST',
    },
    token
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

export const apiUserStats = async (token?: string): Promise<UserStats> => {
  const authToken = token || localStorage.getItem('session_token') || '';
  const [backendStats, backendSettings] = await Promise.all([
    fetchApi<BackendStats>('/user/stats', {}, authToken),
    fetchApi<BackendSettings>('/user/settings', {}, authToken),
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
  
  // Get user_id from localStorage (stored during auth) or use 0 as fallback
  const userId = parseInt(localStorage.getItem('user_id') || '0', 10);
  
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

export const apiUserSettings = async (token?: string): Promise<UserSettings> => {
  const authToken = token || localStorage.getItem('session_token') || '';
  const backendSettings = await fetchApi<BackendSettings>('/user/settings', {}, authToken);
  
  // Get user_id from localStorage (stored during auth) or use 0 as fallback
  const userId = parseInt(localStorage.getItem('user_id') || '0', 10);
  
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