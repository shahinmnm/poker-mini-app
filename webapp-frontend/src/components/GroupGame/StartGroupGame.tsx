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
      // Ensure chatList is always an array
      setChats(Array.isArray(chatList) ? chatList : []);
      
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
      const errorMsg = e.message || e.detail || 'Failed to start group game';
      // Check if bot is not a member of the group
      if (errorMsg.toLowerCase().includes('not a member') || 
          errorMsg.toLowerCase().includes('add the bot')) {
        setError('⚠️ Bot is not a member of this group. Please add the bot to the group first, then try again.');
      } else {
        setError(errorMsg);
      }
      webApp?.HapticFeedback?.impactOccurred('heavy');
    } finally {
      setLoading(false);
    }
  };

  const handleSendToGroup = () => {
    if (!gameInfo) return;
    
    // Create a share link that opens Telegram
    const shareText = `🎮 Join my Poker Game!\n\nGame ID: ${gameInfo.game_id}\n\nTap the button below to join!`;
    const telegramUrl = `https://t.me/share/url?url=${encodeURIComponent(window.location.href)}&text=${encodeURIComponent(shareText)}`;
    
    // Open Telegram share dialog
    try {
      if (webApp?.openTelegramLink) {
        webApp.openTelegramLink(telegramUrl);
      } else if (webApp?.openLink) {
        webApp.openLink(telegramUrl);
      } else {
        // Fallback: open in new window
        window.open(telegramUrl, '_blank');
      }
      webApp?.HapticFeedback?.impactOccurred('light');
    } catch (e) {
      console.error('Failed to open Telegram link:', e);
      // Fallback
      window.open(telegramUrl, '_blank');
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
            <strong>Players:</strong> {Array.isArray(gameInfo.players) ? gameInfo.players.length : 0}/{gameInfo.min_players}+
          </p>
          <div className="players-list">
            {Array.isArray(gameInfo.players) && gameInfo.players.map((player) => (
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
        <div style={{ display: 'flex', gap: '0.5rem', flexDirection: 'column' }}>
          <button
            className="btn-primary"
            onClick={handleSendToGroup}
            style={{ width: '100%' }}
          >
            📤 Send to Group
          </button>
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
      </div>
    );
  }

  return (
    <div className="start-group-game">
      <h3>🎮 Start Group Game</h3>
      <p className="description">
        Start a poker game in a Telegram group. The bot will send a message with join buttons.
      </p>

      {error && (
        <div className="error-message" style={{
          background: 'var(--error-bg, #fee)',
          color: 'var(--error, #c00)',
          padding: '0.75rem',
          borderRadius: '0.5rem',
          marginBottom: '1rem',
          fontSize: '0.9rem',
        }}>
          {error}
        </div>
      )}

      {Array.isArray(chats) && chats.length > 0 ? (
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
          <small style={{ 
            display: 'block', 
            marginTop: '0.5rem', 
            color: 'var(--text-dim, #666)', 
            fontSize: '0.85rem' 
          }}>
            💡 Tip: Make sure the bot is added to your group first! 
            You can find the chat ID by forwarding a message from the group to a chat ID finder bot.
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

