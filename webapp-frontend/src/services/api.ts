import { GameState, GameListItem, AuthResponse, GameAction } from '../types/game.types';

const API_BASE_URL = (import.meta as any).env?.VITE_API_URL || 'https://poker.shahin8n.sbs/api';

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

  if (token) {
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
  return fetchApi<GroupGameInfo>(
    '/group-game/start',
    {
      method: 'POST',
      body: JSON.stringify({ chat_id: chatId, miniapp_url: miniappUrl }),
    },
    token
  );
};

export const joinGroupGame = async (
  gameId: string,
  token: string,
  userName?: string
): Promise<GroupGameInfo> => {
  return fetchApi<GroupGameInfo>(
    '/group-game/join',
    {
      method: 'POST',
      body: JSON.stringify({ game_id: gameId, user_name: userName }),
    },
    token
  );
};

export const getGroupGame = async (
  gameId: string,
  token: string
): Promise<GroupGameInfo> => {
  return fetchApi<GroupGameInfo>(`/group-game/${gameId}`, {}, token);
};

export const listUserChats = async (token: string): Promise<ChatInfo[]> => {
  return fetchApi<ChatInfo[]>('/group-game/chats/list', {}, token);
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