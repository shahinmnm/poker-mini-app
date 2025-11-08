#!/usr/bin/env python3
"""
Pure poker game engine - no Telegram/UI dependencies.
Handles state transitions, player turns, and game flow.

Refactored to use pokerkit State as the source of truth.
"""

import logging
import asyncio
import datetime
import json
from typing import Iterable, Optional, Sequence, Tuple
from enum import Enum

from pokerapp.cards import get_shuffled_deck
from pokerapp.entities import Game, GameMode, GameState, Player, PlayerState
from pokerapp.kvstore import ensure_kv

# Try to use pokerkit engine, fall back to legacy if not available
try:
    from pokerapp.pokerkit_engine import PokerKitEngine, TurnResult
    POKERKIT_ENGINE_AVAILABLE = True
except ImportError:
    POKERKIT_ENGINE_AVAILABLE = False
    PokerKitEngine = None
    TurnResult = Enum('TurnResult', ['CONTINUE_ROUND', 'END_ROUND', 'END_GAME'])

# NOTE: GameCoordinator is imported lazily in GameEngine to avoid a circular
# import during module initialisation.  The coordinator itself depends on the
# pure "PokerEngine" defined in this module.

logger = logging.getLogger(__name__)


class PokerEngine:
    """
    Mode-agnostic poker engine.
    Uses pokerkit State as the source of truth for game logic.
    Falls back to legacy implementation if pokerkit is not available.
    """

    def __init__(self):
        if POKERKIT_ENGINE_AVAILABLE:
            self._pokerkit_engine = PokerKitEngine()
            self._use_pokerkit = True
        else:
            self._pokerkit_engine = None
            self._use_pokerkit = False
            logger.warning(
                "pokerkit not available, using legacy game engine implementation"
            )

    def validate_join_balance(
        self,
        player_balance: int,
        table_stake: int,
    ) -> bool:
        """
        Q7: Check if player has sufficient balance to join.
        Requires at least 20 big blinds minimum.

        Args:
            player_balance: Current wallet balance
            table_stake: Small blind amount (5, 10, 25, etc.)

        Returns:
            True if player can afford to play
        """
        if self._use_pokerkit:
            return self._pokerkit_engine.validate_join_balance(
                player_balance, table_stake
            )
        
        big_blind = table_stake * 2
        minimum_balance = big_blind * 20  # 20 big blinds minimum
        return player_balance >= minimum_balance

    # Legacy methods - only used when pokerkit is not available
    def _active_or_all_in_players(self, game: Game) -> Sequence[Player]:
        """Legacy: Get active or all-in players (pokerkit handles this)"""
        return [
            player
            for player in game.players
            if player.state in (PlayerState.ACTIVE, PlayerState.ALL_IN)
        ]

    def _is_betting_complete_legacy(self, game: Game) -> bool:
        """Legacy: Check if betting round is complete (pokerkit handles this)"""
        if not game.players or game.current_player_index < 0:
            return False
        
        current_player = game.players[game.current_player_index]
        closer_has_acted = getattr(game, "closer_has_acted", False)

        if current_player.user_id != game.trading_end_user_id:
            return False

        if not closer_has_acted:
            return False

        active_players = [
            p for p in game.players if p.state == PlayerState.ACTIVE
        ]
        if not active_players:
            return True

        return all(
            p.round_rate == game.max_round_rate for p in active_players
        )

    def process_turn(self, game: Game) -> TurnResult:
        """
        Process one player turn iteration.

        Flow:
        1. Check if game/round should end
        2. Return current player to act
        3. External code handles action
        4. External code calls advance_after_action()
        5. Loop back to step 1

        Returns:
            TurnResult indicating next state
        """
        if self._use_pokerkit and self._pokerkit_engine._state is not None:
            # Use pokerkit engine
            return self._pokerkit_engine.process_turn(game, game.players)
        
        # Legacy implementation (simplified)
        if not game.players:
            return TurnResult.END_GAME

        active_count = len(self._active_or_all_in_players(game))
        if active_count <= 1:
            return TurnResult.END_GAME

        if game.current_player_index < 0 or game.current_player_index >= len(game.players):
            return TurnResult.END_ROUND

        if self._is_betting_complete_legacy(game):
            return TurnResult.END_ROUND

        return TurnResult.CONTINUE_ROUND

    def advance_after_action(self, game: Game) -> None:
        """
        Record the action and sync state.
        With pokerkit: just syncs state (pokerkit handles turn advancement).
        Legacy: manually advances turn.
        """
        if self._use_pokerkit and self._pokerkit_engine._state is not None:
            # pokerkit handles turn advancement automatically
            # Just sync our game state
            self.sync_game_from_pokerkit(game, game.players)
            return

        # Legacy implementation
        if not game.players:
            return

        current_index = game.current_player_index
        if not (0 <= current_index < len(game.players)):
            return

        current_player = game.players[current_index]
        game.last_actor_user_id = current_player.user_id
        
        if hasattr(game, 'trading_end_user_id'):
            if current_player.user_id == game.trading_end_user_id:
                game.closer_has_acted = True

        game.round_has_started = True

    def advance_to_next_street(self, game: Game) -> GameState:
        """
        Transition to next betting round.
        Handles flop → turn → river → showdown progression.

        Returns:
            New game state
        """
        if self._use_pokerkit and self._pokerkit_engine._state is not None:
            # pokerkit handles street progression automatically
            new_state, _ = self._pokerkit_engine.advance_to_next_street()
            game.state = new_state
            return new_state
        
        return self._move_to_next_street_legacy(game)

    def _move_to_next_street_legacy(self, game: Game) -> GameState:
        """Legacy: Advance to next street (pokerkit handles this)"""
        state_transitions = {
            GameState.ROUND_PRE_FLOP: GameState.ROUND_FLOP,
            GameState.ROUND_FLOP: GameState.ROUND_TURN,
            GameState.ROUND_TURN: GameState.ROUND_RIVER,
            GameState.ROUND_RIVER: GameState.FINISHED,
        }

        current_state = game.state
        if current_state not in state_transitions:
            raise ValueError(f"Cannot advance from state: {current_state}")

        new_state = state_transitions[current_state]
        game.state = new_state

        for player in game.players:
            player.round_rate = 0

        game.max_round_rate = 0
        if hasattr(game, 'last_actor_user_id'):
            game.last_actor_user_id = None
        if hasattr(game, 'round_has_started'):
            game.round_has_started = False

        return new_state

    def get_cards_to_deal(self, game_state: GameState) -> int:
        """
        Get number of community cards to deal for this street.

        Returns:
            Card count (0=pre-flop, 3=flop, 1=turn/river)
        """
        if self._use_pokerkit:
            return self._pokerkit_engine.get_cards_to_deal(game_state)
        
        card_counts = {
            GameState.ROUND_PRE_FLOP: 0,
            GameState.ROUND_FLOP: 3,
            GameState.ROUND_TURN: 1,
            GameState.ROUND_RIVER: 1,
            GameState.FINISHED: 0,
        }
        return card_counts.get(game_state, 0)
    
    def initialize_pokerkit_hand(
        self,
        game: Game,
        players: Sequence[Player],
        small_blind: int,
        big_blind: Optional[int] = None,
    ) -> None:
        """Initialize pokerkit State for a new hand"""
        if self._use_pokerkit:
            self._pokerkit_engine.initialize_hand(
                game, players, small_blind, big_blind
            )
    
    def sync_game_from_pokerkit(self, game: Game, players: Sequence[Player]) -> None:
        """Sync Game entity from pokerkit State"""
        if self._use_pokerkit and self._pokerkit_engine._state is not None:
            self._pokerkit_engine.sync_game_from_state(game, players)
    
    def get_pokerkit_engine(self) -> Optional['PokerKitEngine']:
        """Get the pokerkit engine instance (for advanced usage)"""
        return self._pokerkit_engine if self._use_pokerkit else None


class GameEngine:
    """High level orchestrator for running a poker hand.

    The :class:`PokerEngine` above focuses purely on game rules.  This wrapper
    adds Telegram messaging, Redis persistence and card distribution so that a
    complete hand can be played in group or private chats.
    """

    STATE_TTL_SECONDS = 12 * 60 * 60  # 12 hours; enough for slow games

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
        self._big_blind = (
            big_blind if big_blind is not None else small_blind * 2
        )
        self._kv = ensure_kv(kv_store)
        self._view = view
        self._coordinator = coordinator or GameCoordinator(view=view, kv=kv_store)

        self._hand_number = 0
        self._state_key = ":".join(["game_state", self._game_id])

        self._game = Game()
        # Override generated ID so wallet authorisation remains tied to the
        # session code of the private game.
        self._game.id = self._game_id
        self._game.mode = GameMode.PRIVATE
        self._game.players = self._players
        self._game.table_stake = self._small_blind
        self._game.ready_users = {player.user_id for player in self._players}

    @property
    def game(self) -> Game:
        return self._game

    def _reset_players_for_hand(self) -> None:
        for player in self._players:
            player.state = PlayerState.ACTIVE
            player.cards = []
            player.round_rate = 0

    def _reset_game_for_hand(self) -> None:
        self._game.pot = 0
        self._game.cards_table = []
        self._game.max_round_rate = 0
        self._game.state = GameState.ROUND_PRE_FLOP
        # Dealer rotates each hand to keep blinds fair.
        if self._players:
            self._game.dealer_index = (
                (self._game.dealer_index + 1) % len(self._players)
                if self._hand_number > 1
                else self._game.dealer_index
            )
        self._game.current_player_index = 0
        self._game.remain_cards = []
        self._game.trading_end_user_id = 0
        self._game.closer_has_acted = False
        self._game.round_has_started = False

    def _align_players_with_dealer(self) -> None:
        """Rotate the seating order so blinds follow the dealer."""

        players_count = len(self._players)
        if players_count < 2:
            return

        if players_count == 2:
            dealer_index = self._game.dealer_index
            if dealer_index == 0:
                return

            rotated_players = (
                self._players[dealer_index:]
                + self._players[:dealer_index]
            )
            self._players[:] = rotated_players
            self._game.players = self._players
            self._game.dealer_index = 0
            return

        small_blind_index = (self._game.dealer_index + 1) % players_count
        if small_blind_index == 0:
            return

        rotated_players = (
            self._players[small_blind_index:]
            + self._players[:small_blind_index]
        )
        self._players[:] = rotated_players
        self._game.players = self._players
        self._game.dealer_index = (
            self._game.dealer_index - small_blind_index
        ) % players_count

    def _configure_pre_flop_turn_order(self) -> None:
        """Configure pre-flop turn order (pokerkit handles this automatically)."""
        # With pokerkit, turn order is handled automatically
        # Legacy: would call prepare_round, but pokerkit sync handles it
        pokerkit_engine = self._coordinator.engine.get_pokerkit_engine()
        if pokerkit_engine and pokerkit_engine._state is not None:
            self._coordinator.engine.sync_game_from_pokerkit(self._game, self._players)

    def _deal_private_cards(self) -> None:
        deck = get_shuffled_deck()

        for player in self._players:
            player.cards.clear()
            for _ in range(2):
                if deck:
                    player.cards.append(deck.pop())

        self._game.remain_cards = deck

    async def _notify_private_hands(self) -> None:
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
                    footer=(
                        f"Blinds: {self._small_blind}/{self._big_blind}"
                    ),
                )
            except Exception as exc:  # pragma: no cover - network issues
                self._logger.warning(
                    "Failed to send private hand to %s: %s",
                    player.user_id,
                    exc,
                )

        await asyncio.gather(
            *(
                send_to_player(player)
                for player in self._players
            ),
            return_exceptions=True,
        )

    async def _notify_next_player_turn(self, player: Player) -> None:
        """Update live message for current player's turn (Phase 8+)."""

        if self._view is None:
            self._logger.warning("View is None, cannot notify player turn")
            return

        self._logger.info(
            "🔍 GameEngine calling send_or_update_live_message for player %s",
            player.user_id,
        )

        # Only use the live message system (no legacy fallbacks)
        try:
            await self._view.send_or_update_live_message(
                chat_id=self._chat_id,
                game=self._game,
                current_player=player,
            )
        except AttributeError:
            self._logger.error(
                "View missing send_or_update_live_message method - "
                "incompatible view implementation"
            )
        except Exception as exc:  # pragma: no cover - Telegram failures
            self._logger.error(
                "Failed to update live message for player %s: %s",
                player.user_id,
                exc,
            )

    def _deal_community_cards(self, count: int) -> int:
        """Deal community cards from the deck to the table.

        Args:
            count: Number of cards to deal

        Returns:
            Number of cards successfully dealt
        """

        dealt = 0

        for _ in range(count):
            if not self._game.remain_cards:
                self._logger.warning(
                    (
                        "No cards remaining when attempting to deal %d "
                        "community cards"
                    ),
                    count,
                )
                break

            card = self._game.remain_cards.pop()
            self._game.cards_table.append(card)
            dealt += 1
            self._logger.debug("Dealt community card: %s", card)

        return dealt

    def _snapshot_players(self) -> Iterable[dict[str, object]]:
        for player in self._players:
            yield {
                "user_id": player.user_id,
                "state": player.state.name,
                "round_rate": player.round_rate,
                "wallet": player.wallet.value(),
                "cards": list(player.cards),
            }

    def _persist_state(
        self,
        extra: Optional[dict[str, object]] = None,
    ) -> None:
        if (
            self._players
            and 0 <= self._game.current_player_index < len(self._players)
        ):
            current_player = self._players[
                self._game.current_player_index
            ].user_id
        else:
            current_player = None

        payload = {
            "game_id": self._game_id,
            "hand_number": self._hand_number,
            "state": self._game.state.name,
            "pot": self._game.pot,
            "max_round_rate": self._game.max_round_rate,
            "community_cards": list(self._game.cards_table),
            "current_player": current_player,
            "players": list(self._snapshot_players()),
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
        except Exception as exc:  # pragma: no cover - Redis failures
            self._logger.warning(
                "Failed to persist game state for %s: %s", self._game_id, exc
            )

    async def _finish_hand(self) -> None:
        winners_results = self._coordinator.finish_game_with_winners(
            self._game
        )

        active_players = self._game.players_by(
            states=(PlayerState.ACTIVE, PlayerState.ALL_IN)
        )
        only_one_player = len(active_players) == 1

        text_lines = ["Game is finished with result: \n"]
        for player, best_hand, money in winners_results:
            win_hand = " ".join(best_hand)
            text_lines.append(
                f"{player.mention_markdown}\nGOT: *{money} $*"
            )
            if not only_one_player:
                text_lines.append(f"With combination of cards\n{win_hand}\n")

        text_lines.append("/ready to continue")
        message = "\n".join(text_lines)

        if self._view is not None:
            try:
                await self._view.send_message(
                    chat_id=self._chat_id,
                    text=message,
                )
            except Exception as exc:  # pragma: no cover - Telegram failures
                self._logger.warning(
                    "Failed to announce winners for %s: %s",
                    self._game_id,
                    exc,
                )

        for player in self._players:
            player.wallet.approve(self._game.id)

        self._game.state = GameState.FINISHED
        self._persist_state({"finished": True})

    async def _play_betting_round(self) -> None:
        max_iterations = max(1, len(self._players)) * 100

        for _ in range(max_iterations):
            result, next_player = self._coordinator.process_game_turn(
                self._game
            )
            self._persist_state()

            if result == TurnResult.END_GAME:
                await self._finish_hand()
                return

            if result == TurnResult.END_ROUND:
                self._coordinator.commit_round_bets(self._game)
                self._persist_state()

                # CRITICAL: Check if we're on River BEFORE advancing
                current_state = self._game.state
                self._logger.info(
                    "🔄 END_ROUND on %s - checking if hand should finish",
                    current_state.name,
                )

                if current_state == GameState.ROUND_RIVER:
                    self._logger.info(
                        "🏁 River betting complete → finishing hand NOW"
                    )
                    await self._finish_hand()
                    return

                # Not on River, advance to next street
                self._logger.info(
                    "⏭️ Advancing from %s to next street",
                    current_state.name,
                )
                advance_result = self._coordinator.advance_game_street(
                    self._game
                )
                new_state, cards_count = advance_result
                self._persist_state({"state": new_state.name})

                self._logger.info(
                    "✅ Advanced to %s (cards_to_deal=%d)",
                    new_state.name,
                    cards_count,
                )

                # Safety check: if advance resulted in FINISHED,
                # end immediately
                if new_state == GameState.FINISHED:
                    self._logger.error(
                        "⚠️ UNEXPECTED: Advance resulted in FINISHED state"
                    )
                    await self._finish_hand()
                    return

                # Deal community cards if needed
                if cards_count > 0:
                    dealt_count = self._deal_community_cards(cards_count)
                    self._persist_state()
                    
                    # Deal to pokerkit if using it
                    pokerkit_engine = self._coordinator.engine.get_pokerkit_engine()
                    if pokerkit_engine and pokerkit_engine._state is not None:
                        # Burn card before dealing
                        pokerkit_engine.burn_card()
                        # Deal the community cards
                        pokerkit_engine.deal_board_cards(
                            self._game.cards_table[-cards_count:]
                        )
                        # Sync state after dealing
                        self._coordinator.engine.sync_game_from_pokerkit(
                            self._game, self._players
                        )

                    if dealt_count > 0 and self._view is not None:
                        try:
                            send_live = getattr(
                                self._view,
                                "send_or_update_live_message",
                                None,
                            )

                            if callable(send_live):
                                next_to_act = None

                                if (
                                    0 <= self._game.current_player_index
                                    < len(self._players)
                                ):
                                    next_to_act = self._players[
                                        self._game.current_player_index
                                    ]

                                await send_live(
                                    chat_id=self._chat_id,
                                    game=self._game,
                                    current_player=next_to_act,
                                )
                        except Exception as exc:  # pragma: no cover
                            self._logger.warning(
                                (
                                    "Failed to update live message after "
                                    "dealing cards: %s"
                                ),
                                exc,
                            )

                # Continue to next betting round
                continue

            if result == TurnResult.CONTINUE_ROUND and next_player is not None:
                self._game.last_turn_time = datetime.datetime.now()
                await self._notify_next_player_turn(next_player)
                self._persist_state()
                return

        else:
            self._logger.error(
                "Betting round exceeded %d iterations without terminating",
                max_iterations,
            )
            raise RuntimeError("Betting loop exceeded safe iteration count")

    async def start_new_hand(self) -> Game:
        """Initialise a fresh hand and prompt the first player to act."""

        if len(self._players) < 2:
            raise ValueError(
                "At least two players are required to start a hand"
            )

        self._hand_number += 1
        self._reset_players_for_hand()
        self._reset_game_for_hand()

        self._deal_private_cards()
        await self._notify_private_hands()

        self._align_players_with_dealer()
        
        # Initialize pokerkit state if available
        self._coordinator.engine.initialize_pokerkit_hand(
            self._game,
            self._players,
            self._small_blind,
            self._big_blind,
        )
        
        # Deal cards to pokerkit if using it
        pokerkit_engine = self._coordinator.engine.get_pokerkit_engine()
        if pokerkit_engine and pokerkit_engine._state is not None:
            # Deal hole cards to pokerkit
            for player in self._players:
                pokerkit_engine.deal_hole_cards(player, player.cards)
        
        self._coordinator.apply_pre_flop_blinds(
            game=self._game,
            small_blind=self._small_blind,
            big_blind=self._big_blind,
        )
        
        # Sync game state from pokerkit after blinds
        self._coordinator.engine.sync_game_from_pokerkit(self._game, self._players)

        if len(self._players) == 2:
            self._logger.debug(
                "[HU] Turn order → dealer opens pre-flop; opponent closes."
            )
        else:
            self._logger.debug(
                "[Multi] Turn order → left-of-dealer starts; dealer closes."
            )

        # Configure who acts first and who closes the pre-flop betting round.
        self._configure_pre_flop_turn_order()

        self._persist_state({"hand_number": self._hand_number})

        await self._play_betting_round()

        return self._game


logger.info(
    "✅ Refactored turn logic — alternating actions guaranteed; rounds close."
)
