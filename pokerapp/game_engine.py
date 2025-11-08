#!/usr/bin/env python3
"""
Pure poker game engine - uses pokerkit State as the ONLY source of truth.
All legacy logic has been removed - pokerkit is mandatory.
"""

import logging
import asyncio
import datetime
import json
from typing import Iterable, Optional, Sequence, Tuple

from pokerapp.cards import get_shuffled_deck
from pokerapp.entities import Game, GameMode, GameState, Player, PlayerState
from pokerapp.kvstore import ensure_kv
from pokerapp.pokerkit_engine import PokerKitEngine, TurnResult

# NOTE: GameCoordinator is imported lazily in GameEngine to avoid a circular
# import during module initialisation.

logger = logging.getLogger(__name__)


class PokerEngine:
    """
    Poker engine using pokerkit State as the ONLY source of truth.
    All game logic is handled by pokerkit - this is just a thin wrapper.
    """

    def __init__(self):
        self._pokerkit_engine = PokerKitEngine()

    def validate_join_balance(
        self,
        player_balance: int,
        table_stake: int,
    ) -> bool:
        """Check if player has sufficient balance to join (20 big blinds minimum)."""
        return self._pokerkit_engine.validate_join_balance(player_balance, table_stake)

    def process_turn(self, game: Game) -> TurnResult:
        """Process one player turn iteration using pokerkit."""
        return self._pokerkit_engine.process_turn(game, game.players)

    def advance_after_action(self, game: Game) -> None:
        """Sync game state from pokerkit after an action."""
        self._pokerkit_engine.sync_game_from_state(game, game.players)

    def advance_to_next_street(self, game: Game) -> GameState:
        """Advance to next betting round using pokerkit."""
        new_state, _ = self._pokerkit_engine.advance_to_next_street()
        game.state = new_state
        return new_state

    def get_cards_to_deal(self, game_state: GameState) -> int:
        """Get number of community cards to deal for this street."""
        return self._pokerkit_engine.get_cards_to_deal(game_state)
    
    def initialize_pokerkit_hand(
        self,
        game: Game,
        players: Sequence[Player],
        small_blind: int,
        big_blind: Optional[int] = None,
    ) -> None:
        """Initialize pokerkit State for a new hand."""
        self._pokerkit_engine.initialize_hand(game, players, small_blind, big_blind)
    
    def sync_game_from_pokerkit(self, game: Game, players: Sequence[Player]) -> None:
        """Sync Game entity from pokerkit State."""
        self._pokerkit_engine.sync_game_from_state(game, players)
    
    def get_pokerkit_engine(self) -> PokerKitEngine:
        """Get the pokerkit engine instance."""
        return self._pokerkit_engine


class GameEngine:
    """
    High level orchestrator for running a poker hand using pokerkit.
    Handles Telegram messaging, Redis persistence and card distribution.
    """

    STATE_TTL_SECONDS = 12 * 60 * 60  # 12 hours

    def __init__(
        self,
        *,
        game_id: str,
        chat_id: int,
        players: Sequence[Player],
        small_blind: int,
        big_blind: Optional[int] = None,
        kv_store=None,
        view=None,
        coordinator=None,
    ) -> None:
        from pokerapp.game_coordinator import GameCoordinator  # local import

        self._logger = logging.getLogger(__name__)
        self._game_id = str(game_id)
        self._chat_id = chat_id
        self._players: list[Player] = list(players)
        self._small_blind = small_blind
        self._big_blind = big_blind if big_blind is not None else small_blind * 2
        self._kv = ensure_kv(kv_store)
        self._view = view
        self._coordinator = coordinator or GameCoordinator(view=view, kv=kv_store)

        self._hand_number = 0
        self._state_key = ":".join(["game_state", self._game_id])

        self._game = Game()
        self._game.id = self._game_id
        self._game.mode = GameMode.PRIVATE
        self._game.players = self._players
        self._game.table_stake = self._small_blind
        self._game.ready_users = {player.user_id for player in self._players}

    @property
    def game(self) -> Game:
        return self._game

    def _reset_players_for_hand(self) -> None:
        """Reset player state for new hand."""
        for player in self._players:
            player.state = PlayerState.ACTIVE
            player.cards = []
            player.round_rate = 0

    def _reset_game_for_hand(self) -> None:
        """Reset game state for new hand."""
        self._game.pot = 0
        self._game.cards_table = []
        self._game.max_round_rate = 0
        self._game.state = GameState.ROUND_PRE_FLOP
        
        # Rotate dealer
        if self._players:
            self._game.dealer_index = (
                (self._game.dealer_index + 1) % len(self._players)
                if self._hand_number > 1
                else self._game.dealer_index
            )
        
        self._game.current_player_index = 0
        self._game.remain_cards = []

    def _deal_private_cards(self) -> None:
        """Deal hole cards to all players."""
        deck = get_shuffled_deck()
        for player in self._players:
            player.cards.clear()
            for _ in range(2):
                if deck:
                    player.cards.append(deck.pop())
        self._game.remain_cards = deck

    async def _notify_private_hands(self) -> None:
        """Send private hand messages to players."""
        if self._view is None:
            return

        async def send_to_player(player: Player) -> None:
            try:
                await self._view.send_or_update_private_hand(
                    chat_id=player.user_id,
                    cards=player.cards,
                    table_cards=self._game.cards_table,
                    mention_markdown=player.mention_markdown,
                    disable_notification=False,
                    footer=f"Blinds: {self._small_blind}/{self._big_blind}",
                )
            except Exception as exc:
                self._logger.warning(
                    "Failed to send private hand to %s: %s", player.user_id, exc
                )

        await asyncio.gather(
            *(send_to_player(player) for player in self._players),
            return_exceptions=True,
        )

    async def _notify_next_player_turn(self, player: Player) -> None:
        """Update live message for current player's turn."""
        if self._view is None:
            return

        try:
            await self._view.send_or_update_live_message(
                chat_id=self._chat_id,
                game=self._game,
                current_player=player,
            )
        except Exception as exc:
            self._logger.error(
                "Failed to update live message for player %s: %s",
                player.user_id,
                exc,
            )

    def _deal_community_cards(self, count: int) -> int:
        """Deal community cards from deck."""
        dealt = 0
        for _ in range(count):
            if not self._game.remain_cards:
                break
            card = self._game.remain_cards.pop()
            self._game.cards_table.append(card)
            dealt += 1
        return dealt

    def _persist_state(self, extra: Optional[dict[str, object]] = None) -> None:
        """Persist game state to Redis."""
        current_player = None
        if (
            self._players
            and 0 <= self._game.current_player_index < len(self._players)
        ):
            current_player = self._players[self._game.current_player_index].user_id

        payload = {
            "game_id": self._game_id,
            "hand_number": self._hand_number,
            "state": self._game.state.name,
            "pot": self._game.pot,
            "max_round_rate": self._game.max_round_rate,
            "community_cards": list(self._game.cards_table),
            "current_player": current_player,
            "players": [
                {
                    "user_id": p.user_id,
                    "state": p.state.name,
                    "round_rate": p.round_rate,
                    "wallet": p.wallet.value(),
                    "cards": list(p.cards),
                }
                for p in self._players
            ],
            "updated_at": datetime.datetime.now().isoformat(),
        }

        if extra:
            payload.update(extra)

        try:
            self._kv.set(
                self._state_key,
                json.dumps(payload),
                ex=self.STATE_TTL_SECONDS,
            )
        except Exception as exc:
            self._logger.warning(
                "Failed to persist game state for %s: %s", self._game_id, exc
            )

    async def _finish_hand(self) -> None:
        """Finish hand and announce winners."""
        winners_results = self._coordinator.finish_game_with_winners(self._game)

        active_players = self._game.players_by(
            states=(PlayerState.ACTIVE, PlayerState.ALL_IN)
        )
        only_one_player = len(active_players) == 1

        text_lines = ["Game is finished with result: \n"]
        for player, best_hand, money in winners_results:
            win_hand = " ".join(best_hand)
            text_lines.append(f"{player.mention_markdown}\nGOT: *{money} $*")
            if not only_one_player:
                text_lines.append(f"With combination of cards\n{win_hand}\n")

        text_lines.append("/ready to continue")
        message = "\n".join(text_lines)

        if self._view is not None:
            try:
                await self._view.send_message(chat_id=self._chat_id, text=message)
            except Exception as exc:
                self._logger.warning(
                    "Failed to announce winners for %s: %s", self._game_id, exc
                )

        for player in self._players:
            player.wallet.approve(self._game.id)

        self._game.state = GameState.FINISHED
        self._persist_state({"finished": True})

    async def _play_betting_round(self) -> None:
        """Play one betting round using pokerkit."""
        max_iterations = max(1, len(self._players)) * 100

        for _ in range(max_iterations):
            result, next_player = self._coordinator.process_game_turn(self._game)
            self._persist_state()

            if result == TurnResult.END_GAME:
                await self._finish_hand()
                return

            if result == TurnResult.END_ROUND:
                self._coordinator.commit_round_bets(self._game)
                self._persist_state()

                if self._game.state == GameState.ROUND_RIVER:
                    await self._finish_hand()
                    return

                # Advance to next street
                new_state, cards_count = self._coordinator.advance_game_street(
                    self._game
                )
                self._persist_state({"state": new_state.name})

                if new_state == GameState.FINISHED:
                    await self._finish_hand()
                    return

                # Deal community cards
                if cards_count > 0:
                    dealt_count = self._deal_community_cards(cards_count)
                    self._persist_state()

                    # Deal to pokerkit
                    pokerkit_engine = self._coordinator.engine.get_pokerkit_engine()
                    if pokerkit_engine._state is not None:
                        pokerkit_engine.burn_card()
                        pokerkit_engine.deal_board_cards(
                            self._game.cards_table[-cards_count:]
                        )
                        self._coordinator.engine.sync_game_from_pokerkit(
                            self._game, self._players
                        )

                    if dealt_count > 0 and self._view is not None:
                        try:
                            next_to_act = None
                            if (
                                0 <= self._game.current_player_index
                                < len(self._players)
                            ):
                                next_to_act = self._players[
                                    self._game.current_player_index
                                ]

                            await self._view.send_or_update_live_message(
                                chat_id=self._chat_id,
                                game=self._game,
                                current_player=next_to_act,
                            )
                        except Exception as exc:
                            self._logger.warning(
                                "Failed to update live message: %s", exc
                            )

                continue

            if result == TurnResult.CONTINUE_ROUND and next_player is not None:
                self._game.last_turn_time = datetime.datetime.now()
                await self._notify_next_player_turn(next_player)
                self._persist_state()
                return

        else:
            self._logger.error(
                "Betting round exceeded %d iterations", max_iterations
            )
            raise RuntimeError("Betting loop exceeded safe iteration count")

    async def start_new_hand(self) -> Game:
        """Initialize a fresh hand and start betting round."""
        if len(self._players) < 2:
            raise ValueError("At least two players required")

        self._hand_number += 1
        self._reset_players_for_hand()
        self._reset_game_for_hand()

        self._deal_private_cards()
        await self._notify_private_hands()

        # Initialize pokerkit state
        self._coordinator.engine.initialize_pokerkit_hand(
            self._game,
            self._players,
            self._small_blind,
            self._big_blind,
        )

        # Deal cards to pokerkit
        pokerkit_engine = self._coordinator.engine.get_pokerkit_engine()
        for player in self._players:
            pokerkit_engine.deal_hole_cards(player, player.cards)

        # Apply blinds (pokerkit handles this automatically)
        self._coordinator.apply_pre_flop_blinds(
            game=self._game,
            small_blind=self._small_blind,
            big_blind=self._big_blind,
        )

        # Sync state after initialization
        self._coordinator.engine.sync_game_from_pokerkit(self._game, self._players)

        self._persist_state({"hand_number": self._hand_number})

        await self._play_betting_round()

        return self._game
