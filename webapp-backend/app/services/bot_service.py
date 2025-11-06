"""Service for communicating with the Telegram bot to send messages and manage group games."""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional, Any

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class BotService:
    """Service to interact with Telegram Bot API for group game management."""

    def __init__(self, bot_token: Optional[str] = None):
        """Initialize bot service with token."""
        self._token = bot_token or os.getenv("POKERBOT_TOKEN", "")
        if not self._token:
            logger.warning("POKERBOT_TOKEN not set, bot service will be limited")
        self._bot: Optional[Bot] = None

    def _get_bot(self) -> Bot:
        """Get or create bot instance."""
        if self._bot is None:
            if not self._token:
                raise ValueError("Bot token not configured")
            self._bot = Bot(token=self._token)
        return self._bot

    async def send_group_game_invite(
        self,
        chat_id: int,
        initiator_name: str,
        game_id: str,
        miniapp_url: Optional[str] = None,
    ) -> Optional[int]:
        """
        Send a group game invite message to a Telegram group.

        Args:
            chat_id: Telegram group chat ID
            initiator_name: Name of the player who started the game
            game_id: Unique game identifier
            miniapp_url: Optional URL to the mini-app

        Returns:
            Message ID if successful, None otherwise
        """
        try:
            bot = self._get_bot()
            
            # Build message text
            message_text = (
                f"🎮 **Group Poker Game Started!**\n\n"
                f"👤 Started by: {initiator_name}\n"
                f"✅ Tap the button below to join the game!\n\n"
                f"Waiting for players to join..."
            )

            # Build inline keyboard with join button
            keyboard_buttons = [
                [
                    InlineKeyboardButton(
                        text="✅ Tap to Sit",
                        callback_data=f"group_game_join:{game_id}",
                    )
                ]
            ]

            # Add mini-app button if URL provided
            if miniapp_url:
                keyboard_buttons.append(
                    [
                        InlineKeyboardButton(
                            text="🎮 Open Game",
                            web_app={"url": miniapp_url},
                        )
                    ]
                )

            reply_markup = InlineKeyboardMarkup(keyboard_buttons)

            # Send message
            message = await bot.send_message(
                chat_id=chat_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )

            logger.info(
                "Sent group game invite to chat %s, message_id=%s",
                chat_id,
                message.message_id,
            )
            return message.message_id

        except TelegramError as e:
            logger.error(
                "Failed to send group game invite to chat %s: %s",
                chat_id,
                e,
            )
            return None
        except Exception as e:
            logger.error(
                "Unexpected error sending group game invite: %s",
                e,
                exc_info=True,
            )
            return None

    async def update_group_game_message(
        self,
        chat_id: int,
        message_id: int,
        players: List[Dict[str, Any]],
        game_id: str,
        min_players: int = 2,
        miniapp_url: Optional[str] = None,
    ) -> bool:
        """
        Update the group game invite message with current player list.

        Args:
            chat_id: Telegram group chat ID
            message_id: Message ID to update
            players: List of player info dicts with 'id', 'name' keys
            game_id: Game identifier
            min_players: Minimum players needed to start
            miniapp_url: Optional URL to the mini-app

        Returns:
            True if successful, False otherwise
        """
        try:
            bot = self._get_bot()

            player_count = len(players)
            def format_player_name(p: Dict[str, Any]) -> str:
                """Format player name with fallback."""
                name = p.get('name')
                if name:
                    return name
                player_id = p.get('id', '?')
                return f'Player {player_id}'
            
            player_list = "\n".join(
                [f"  • {format_player_name(p)}" for p in players]
            ) if players else "  (No players yet)"

            status_text = (
                f"✅ Ready to start! ({player_count}/{min_players}+)"
                if player_count >= min_players
                else f"⏳ Waiting... ({player_count}/{min_players} players)"
            )

            message_text = (
                f"🎮 **Group Poker Game**\n\n"
                f"**Players:**\n{player_list}\n\n"
                f"{status_text}\n\n"
                f"Tap below to join!"
            )

            # Build keyboard
            keyboard_buttons = [
                [
                    InlineKeyboardButton(
                        text="✅ Tap to Sit",
                        callback_data=f"group_game_join:{game_id}",
                    )
                ]
            ]

            if miniapp_url:
                keyboard_buttons.append(
                    [
                        InlineKeyboardButton(
                            text="🎮 Open Game",
                            web_app={"url": miniapp_url},
                        )
                    ]
                )

            reply_markup = InlineKeyboardMarkup(keyboard_buttons)

            # Update message
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )

            logger.info(
                "Updated group game message %s in chat %s with %d players",
                message_id,
                chat_id,
                player_count,
            )
            return True

        except TelegramError as e:
            logger.error(
                "Failed to update group game message %s in chat %s: %s",
                message_id,
                chat_id,
                e,
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected error updating group game message: %s",
                e,
                exc_info=True,
            )
            return False

    async def get_user_chats(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get list of groups/chats the bot is in (limited by Telegram API).

        Note: Telegram Bot API doesn't provide a direct way to list all groups
        a bot is in. This is a placeholder that could be enhanced with:
        - Storing chat IDs when bot is added to groups
        - Using getUpdates to track group memberships
        - Manual configuration

        Args:
            user_id: Telegram user ID (for future filtering)

        Returns:
            List of chat info dicts
        """
        # This is a limitation of Telegram Bot API - we can't directly
        # list all groups. In production, you'd maintain a database
        # of groups the bot has been added to.
        logger.warning(
            "get_user_chats called but Telegram API doesn't support listing all groups"
        )
        return []

    async def send_miniapp_button_to_group(
        self,
        chat_id: int,
        miniapp_url: str,
        text: str = "🎮 Start Poker Game",
    ) -> Optional[int]:
        """
        Send a message with mini-app button to a group.

        Args:
            chat_id: Telegram group chat ID
            miniapp_url: URL to the mini-app
            text: Message text

        Returns:
            Message ID if successful, None otherwise
        """
        try:
            bot = self._get_bot()

            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        text=text,
                        web_app={"url": miniapp_url},
                    )
                ]
            ])

            message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
            )

            logger.info(
                "Sent mini-app button to chat %s, message_id=%s",
                chat_id,
                message.message_id,
            )
            return message.message_id

        except TelegramError as e:
            logger.error(
                "Failed to send mini-app button to chat %s: %s",
                chat_id,
                e,
            )
            return None
        except Exception as e:
            logger.error(
                "Unexpected error sending mini-app button: %s",
                e,
                exc_info=True,
            )
            return None


# Singleton instance
_bot_service: Optional[BotService] = None


def get_bot_service() -> BotService:
    """Get singleton bot service instance."""
    global _bot_service
    if _bot_service is None:
        _bot_service = BotService()
    return _bot_service

