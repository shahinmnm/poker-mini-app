#!/usr/bin/env python3
"""
Simplified poker game engine using pokerkit library.
Maintains backward compatibility with existing Game and Player entities.
"""

import logging
from typing import Optional, Sequence, Tuple
from enum import Enum

from pokerkit import (
    NoLimitTexasHoldem,
    Automation,
    Mode,
    State as PokerKitState,
)
from pokerapp.entities import Game, GameMode, GameState, Player, PlayerState
from pokerapp.cards import Card

logger = logging.getLogger(__name__)


class TurnResult(Enum):
    """Result of processing a player turn"""
    CONTINUE_ROUND = "continue_round"
    END_ROUND = "end_round"
    END_GAME = "end_game"


class PokerEngine:
    """
    Simplified poker engine using pokerkit.
    Wraps pokerkit State to maintain compatibility with existing Game entity.
    """

    def __init__(self):
        self._pokerkit_state: Optional[PokerKitState] = None
        self._pokerkit_game: Optional[NoLimitTexasHoldem] = None

    def _create_pokerkit_game(
        self,
        small_blind: int,
        big_blind: int,
        player_count: int,
    ) -> NoLimitTexasHoldem:
        """Create a pokerkit game instance."""
        return NoLimitTexasHoldem(
            automations=(
                Automation.ANTE_POSTING,
                Automation.BET_COLLECTION,
                Automation.BLIND_OR_STRADDLE_POSTING,
                Automation.CARD_BURNING,
                Automation.HOLE_CARDS_SHOWING_OR_MUCKING,
                Automation.HAND_KILLING,
                Automation.CHIPS_PUSHING,
                Automation.CHIPS_PULLING,
            ),
            ante_trimming_status=True,
            raw_antes=0,
            raw_blinds_or_straddles=(small_blind, big_blind),
            min_bet=small_blind,
            mode=Mode.CASH_GAME,
        )

    def _sync_game_to_pokerkit(self, game: Game, players: Sequence[Player]) -> None:
        """Sync our Game entity to pokerkit State."""
        if self._pokerkit_state is None:
            return

        # Update stacks from player wallets
        for i, player in enumerate(players):
            if i < len(self._pokerkit_state.stacks):
                # Note: pokerkit manages stacks internally
                # We'll sync round_rate to betting amounts
                pass

        # Sync board cards
        if hasattr(self._pokerkit_state, 'boards') and self._pokerkit_state.boards:
            game.cards_table = list(self._pokerkit_state.boards[0])

    def _sync_pokerkit_to_game(
        self,
        game: Game,
        players: Sequence[Player],
    ) -> None:
        """Sync pokerkit State back to our Game entity."""
        if self._pokerkit_state is None:
            return

        # Update pot
        total_pot = sum(pot.amount for pot in self._pokerkit_state.pots)
        game.pot = total_pot

        # Update board cards
        if hasattr(self._pokerkit_state, 'boards') and self._pokerkit_state.boards:
            game.cards_table = list(self._pokerkit_state.boards[0])

        # Update game state based on street
        street_index = getattr(self._pokerkit_state, 'street_index', 0)
        state_map = {
            0: GameState.ROUND_PRE_FLOP,
            1: GameState.ROUND_FLOP,
            2: GameState.ROUND_TURN,
            3: GameState.ROUND_RIVER,
        }
        if street_index < len(state_map):
            game.state = state_map[street_index]
        else:
            game.state = GameState.FINISHED

        # Update current player index
        actor_index = getattr(self._pokerkit_state, 'actor_index', None)
        if actor_index is not None:
            game.current_player_index = actor_index

    def validate_join_balance(
        self,
        player_balance: int,
        table_stake: int,
    ) -> bool:
        """
        Check if player has sufficient balance to join.
        Requires at least 20 big blinds minimum.
        """
        big_blind = table_stake * 2
        minimum_balance = big_blind * 20
        return player_balance >= minimum_balance

    def initialize_game(
        self,
        game: Game,
        players: Sequence[Player],
        small_blind: int,
        big_blind: int,
    ) -> None:
        """Initialize pokerkit state for a new hand."""
        player_count = len(players)
        starting_stacks = [player.wallet.value() for player in players]

        self._pokerkit_game = self._create_pokerkit_game(
            small_blind, big_blind, player_count
        )
        self._pokerkit_state = self._pokerkit_game(starting_stacks, player_count)

        # Sync initial state
        self._sync_pokerkit_to_game(game, players)

    def _active_players(self, game: Game) -> Sequence[Player]:
        return [
            player
            for player in game.players
            if player.state == PlayerState.ACTIVE
        ]

    def _active_or_all_in_players(self, game: Game) -> Sequence[Player]:
        return [
            player
            for player in game.players
            if player.state in (PlayerState.ACTIVE, PlayerState.ALL_IN)
        ]

    def process_turn(self, game: Game) -> TurnResult:
        """
        Process one player turn iteration using pokerkit.
        """
        if not game.players:
            return TurnResult.END_GAME

        if self._pokerkit_state is None:
            return TurnResult.END_GAME

        # Check if hand is finished
        if not self._pokerkit_state.status:
            return TurnResult.END_GAME

        # Check if betting round is complete
        actor_index = getattr(self._pokerkit_state, 'actor_index', None)
        if actor_index is None:
            # No actor means betting round is complete
            return TurnResult.END_ROUND

        # Count active players
        active_count = len(self._active_or_all_in_players(game))
        if active_count <= 1:
            return TurnResult.END_GAME

        return TurnResult.CONTINUE_ROUND

    def advance_after_action(self, game: Game) -> None:
        """Record the action and move to next player."""
        # Pokerkit handles this automatically through its state machine
        # We just need to sync back
        if self._pokerkit_state:
            self._sync_pokerkit_to_game(game, game.players)

    def advance_to_next_street(self, game: Game) -> GameState:
        """
        Transition to next betting round.
        Pokerkit handles this automatically when betting completes.
        """
        if self._pokerkit_state:
            self._sync_pokerkit_to_game(game, game.players)
        return game.state

    def get_cards_to_deal(self, game_state: GameState) -> int:
        """Get number of community cards to deal for this street."""
        card_counts = {
            GameState.ROUND_PRE_FLOP: 0,
            GameState.ROUND_FLOP: 3,
            GameState.ROUND_TURN: 1,
            GameState.ROUND_RIVER: 1,
            GameState.FINISHED: 0,
        }
        return card_counts.get(game_state, 0)

    def prepare_round(self, game: Game, street: Optional[GameState] = None) -> None:
        """Prepare turn order for a betting round."""
        # Pokerkit handles turn order automatically
        if self._pokerkit_state:
            self._sync_pokerkit_to_game(game, game.players)

    def should_end_round(self, game: Game) -> bool:
        """Check if the current betting round is complete."""
        if self._pokerkit_state is None:
            return True
        
        actor_index = getattr(self._pokerkit_state, 'actor_index', None)
        return actor_index is None
