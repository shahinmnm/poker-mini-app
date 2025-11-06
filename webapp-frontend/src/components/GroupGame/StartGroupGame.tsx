import React, { useState, useEffect } from 'react';
import { useTelegram } from '../../hooks/useTelegram';
import {
  startGroupGame,
  getGroupGame,
  listUserChats,
  sendMiniappToGroup,
  GroupGameInfo,
  ChatInfo,
} from '../../services/api';
// CSS will be handled by global styles or inline styles for now

interface StartGroupGameProps {
  onGameStarted?: (gameId: string) => void;
}

export const StartGroupGame: React.FC<StartGroupGameProps> = ({ onGameStarted }) => {
  const { webApp, user, initData } = useTelegram();
  const [chats, setChats] = useState<ChatInfo[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [gameInfo, setGameInfo] = useState<GroupGameInfo | null>(null);
  const [polling, setPolling] = useState(false);

  // Load available chats
  useEffect(() => {
    if (initData) {
      loadChats();
    }
  }, [initData]);

  // Poll for game status when game is started
  useEffect(() => {
    if (gameInfo && polling) {
      const interval = setInterval(async () => {
        try {
          const updated = await getGroupGame(gameInfo.game_id, initData);
          setGameInfo(updated);
          
          // If game started, stop polling and notify
          if (updated.status === 'active' || updated.status === 'starting') {
            setPolling(false);
            onGameStarted?.(updated.game_id);
          }
        } catch (e: any) {
          console.error('Failed to poll game status:', e);
        }
      }, 2000); // Poll every 2 seconds

      return () => clearInterval(interval);
    }
  }, [gameInfo, polling, initData, onGameStarted]);

  const loadChats = async () => {
    if (!initData) {
      setError('Telegram authentication required. Please refresh the page.');
      return;
    }
    
    try {
      const chatList = await listUserChats(initData);
      setChats(chatList);
      
      // If no chats available, show manual input option
      if (chatList.length === 0) {
        setError('No groups found. You can manually enter a group chat ID.');
      }
    } catch (e: any) {
      console.error('Failed to load chats:', e);
      setError('Could not load groups. You can manually enter a chat ID.');
    }
  };

  const handleStartGame = async () => {
    if (!selectedChatId) {
      setError('Please select a group or enter a chat ID');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const miniappUrl = webApp?.initDataUnsafe?.start_param 
        ? window.location.href 
        : window.location.href;

      const game = await startGroupGame(selectedChatId, initData, miniappUrl);
      setGameInfo(game);
      setPolling(true);
      
      // Send mini-app button to group
      try {
        await sendMiniappToGroup(game.game_id, selectedChatId, initData, miniappUrl);
      } catch (e) {
        console.warn('Failed to send mini-app button:', e);
        // Non-critical, continue
      }

      webApp?.HapticFeedback?.impactOccurred('medium');
    } catch (e: any) {
      setError(e.message || 'Failed to start group game');
      webApp?.HapticFeedback?.impactOccurred('heavy');
    } finally {
      setLoading(false);
    }
  };

  const handleChatIdInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value.trim();
    if (value) {
      const chatId = parseInt(value, 10);
      if (!isNaN(chatId)) {
        setSelectedChatId(chatId);
        setError(null);
      } else {
        setError('Invalid chat ID. Please enter a number.');
      }
    } else {
      setSelectedChatId(null);
    }
  };

  if (gameInfo) {
    return (
      <div className="group-game-status">
        <h3>🎮 Group Game Started!</h3>
        <div className="game-info">
          <p>
            <strong>Status:</strong> {gameInfo.status === 'waiting' ? '⏳ Waiting for players' : 
                                      gameInfo.status === 'starting' ? '🚀 Starting...' : 
                                      '✅ Active'}
          </p>
          <p>
            <strong>Players:</strong> {gameInfo.players.length}/{gameInfo.min_players}+
          </p>
          <div className="players-list">
            {gameInfo.players.map((player) => (
              <div key={player.id} className="player-item">
                • {player.name}
              </div>
            ))}
          </div>
          {gameInfo.status === 'waiting' && (
            <p className="waiting-message">
              Share the game in your group! Players can tap "✅ Tap to Sit" to join.
            </p>
          )}
        </div>
        <button
          className="btn-secondary"
          onClick={() => {
            setGameInfo(null);
            setPolling(false);
            setSelectedChatId(null);
          }}
        >
          Start New Game
        </button>
      </div>
    );
  }

  return (
    <div className="start-group-game">
      <h3>🎮 Start Group Game</h3>
      <p className="description">
        Start a poker game in a Telegram group. The bot will send a message with join buttons.
      </p>

      {error && <div className="error-message">{error}</div>}

      {chats.length > 0 ? (
        <div className="chat-selector">
          <label htmlFor="chat-select">Select a group:</label>
          <select
            id="chat-select"
            value={selectedChatId || ''}
            onChange={(e) => setSelectedChatId(parseInt(e.target.value, 10))}
            className="chat-select"
          >
            <option value="">-- Select a group --</option>
            {chats.map((chat) => (
              <option key={chat.id} value={chat.id}>
                {chat.title || `Group ${chat.id}`}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <div className="chat-input">
          <label htmlFor="chat-id">Enter Group Chat ID:</label>
          <input
            id="chat-id"
            type="number"
            placeholder="e.g., -1001234567890"
            onChange={handleChatIdInput}
            className="chat-id-input"
          />
          <small>
            Find the chat ID by adding the bot to your group and checking bot logs, 
            or use a Telegram chat ID finder bot.
          </small>
        </div>
      )}

      <button
        className="btn-primary"
        onClick={handleStartGame}
        disabled={!selectedChatId || loading}
      >
        {loading ? 'Starting...' : 'Start Group Game'}
      </button>
    </div>
  );
};

