#!/usr/bin/env python3
"""
PokerKit-based game engine - uses pokerkit State as the source of truth.
This replaces much of the custom logic in game_engine.py with pokerkit's proven implementation.
"""

import logging
from typing import Optional, Sequence, Tuple, Dict, List
from math import inf
from enum import Enum

try:
    from pokerkit import (
        NoLimitTexasHoldem,
        Automation,
        Mode,
        State as PokerKitState,
    )
    POKERKIT_AVAILABLE = True
except ImportError:
    POKERKIT_AVAILABLE = False
    NoLimitTexasHoldem = None
    Automation = None
    Mode = None
    PokerKitState = None

from pokerapp.entities import Game, GameMode, GameState, Player, PlayerState
from pokerapp.cards import Cards, cards_to_pokerkit_string, pokerkit_string_to_cards

logger = logging.getLogger(__name__)


class TurnResult(Enum):
    """Result of processing a player turn"""
    CONTINUE_ROUND = "continue_round"
    END_ROUND = "end_round"
    END_GAME = "end_game"


class PokerKitEngine:
    """
    Poker engine using pokerkit State as the source of truth.
    All game logic (turn order, betting, street progression) comes from pokerkit.
    Our Game entity is synced FROM pokerkit State, not the other way around.
    """
    
    def __init__(self):
        if not POKERKIT_AVAILABLE:
            raise ImportError(
                "pokerkit library is required. Install with: pip install pokerkit"
            )
        self._state: Optional[PokerKitState] = None
        self._player_index_map: Dict[str, int] = {}  # user_id -> pokerkit index
        self._reverse_index_map: Dict[int, str] = {}  # pokerkit index -> user_id
    
    def initialize_hand(
        self,
        game: Game,
        players: Sequence[Player],
        small_blind: int,
        big_blind: Optional[int] = None,
    ) -> None:
        """
        Initialize a new hand with pokerkit State.
        
        Args:
            game: Our Game entity (will be synced from pokerkit)
            players: List of players in order
            small_blind: Small blind amount
            big_blind: Big blind amount (defaults to 2x small blind)
        """
        num_players = len(players)
        if num_players < 2:
            raise ValueError("At least 2 players required")
        
        big_blind_amount = big_blind if big_blind is not None else small_blind * 2
        
        # Build starting stacks and player mapping
        starting_stacks = []
        self._player_index_map.clear()
        self._reverse_index_map.clear()
        
        for i, player in enumerate(players):
            stack = player.wallet.value()
            starting_stacks.append(stack if stack > 0 else inf)
            self._player_index_map[player.user_id] = i
            self._reverse_index_map[i] = player.user_id
        
        # Create pokerkit state
        # We disable most automations to have fine-grained control
        self._state = NoLimitTexasHoldem.create_state(
            # Automations - minimal set, we handle most manually
            (
                Automation.BET_COLLECTION,
                Automation.CHIPS_PUSHING,
                Automation.CHIPS_PULLING,
            ),
            False,  # Uniform antes
            {},  # No antes
            (small_blind, big_blind_amount),  # Blinds
            big_blind_amount,  # Min bet
            tuple(starting_stacks),
            num_players,
            mode=Mode.CASH_GAME,
        )
        
        logger.info(
            "Initialized pokerkit hand: %d players, blinds %d/%d",
            num_players,
            small_blind,
            big_blind_amount,
        )
    
    def deal_hole_cards(self, player: Player, cards: Cards) -> None:
        """Deal hole cards to a player"""
        if self._state is None:
            raise RuntimeError("State not initialized. Call initialize_hand() first.")
        
        cards_str = cards_to_pokerkit_string(cards)
        self._state.deal_hole(cards_str)
        
        logger.debug("Dealt hole cards to %s: %s", player.user_id, cards_str)
    
    def deal_board_cards(self, cards: Cards) -> None:
        """Deal community cards"""
        if self._state is None:
            raise RuntimeError("State not initialized")
        
        cards_str = cards_to_pokerkit_string(cards)
        self._state.deal_board(cards_str)
        
        logger.debug("Dealt board cards: %s", cards_str)
    
    def burn_card(self) -> None:
        """Burn a card before dealing"""
        if self._state is None:
            raise RuntimeError("State not initialized")
        
        self._state.burn_card('??')
    
    def sync_game_from_state(self, game: Game, players: Sequence[Player]) -> None:
        """
        Sync our Game entity from pokerkit State.
        This is the primary way to get game state - pokerkit is the source of truth.
        """
        if self._state is None:
            return
        
        # Map pokerkit street to our GameState
        street = self._state.street
        street_name = str(street).lower() if hasattr(street, '__str__') else str(street)
        
        # Map pokerkit street names to our GameState enum
        # pokerkit uses Street objects, we need to check their properties
        street_map = {
            'deal': GameState.ROUND_PRE_FLOP,
            'flop': GameState.ROUND_FLOP,
            'turn': GameState.ROUND_TURN,
            'river': GameState.ROUND_RIVER,
            'showdown': GameState.FINISHED,
        }
        
        # Try to get street name from pokerkit's Street object
        try:
            # pokerkit Street objects have a name attribute or can be converted to string
            if hasattr(street, 'name'):
                street_name = street.name.lower()
            elif hasattr(street, '__str__'):
                street_name = str(street).lower()
        except Exception:
            pass
        
        game.state = street_map.get(street_name, GameState.INITIAL)
        
        # Update pot from pokerkit
        try:
            pots = self._state.pots
            if pots:
                # Sum all pot amounts (raked + unraked)
                total_pot = sum(pot.raked_amount + pot.unraked_amount for pot in pots)
                game.pot = total_pot
        except AttributeError:
            pass
        
        # Update player states and bets
        try:
            stacks = self._state.stacks
            bet_amounts = getattr(self._state, 'bet_amounts', None)
            acting_statuses = getattr(self._state, 'acting_statuses', None)
            
            # Track max round rate
            max_rate = 0
            
            for i, player in enumerate(players):
                if i >= len(stacks):
                    continue
                
                # Update stack (this reflects current wallet balance)
                current_stack = stacks[i]
                
                # Update round rate (current bet this round)
                if bet_amounts and i < len(bet_amounts):
                    player.round_rate = bet_amounts[i]
                    max_rate = max(max_rate, bet_amounts[i])
                else:
                    player.round_rate = 0
                
                # Update player state based on pokerkit
                if acting_statuses and i < len(acting_statuses):
                    # If not acting and has no chips, might be all-in or folded
                    if not acting_statuses[i]:
                        if current_stack == 0 and player.round_rate > 0:
                            player.state = PlayerState.ALL_IN
                        elif player.state == PlayerState.ACTIVE:
                            # Check if folded by comparing with previous state
                            # This is a heuristic - pokerkit doesn't directly expose fold state
                            pass
            
            game.max_round_rate = max_rate
            
            # Update current player index from pokerkit
            if acting_statuses:
                for i, is_acting in enumerate(acting_statuses):
                    if is_acting:
                        game.current_player_index = i
                        break
                else:
                    # No one is acting - round might be complete
                    game.current_player_index = -1
        except AttributeError as e:
            logger.warning("Could not sync all state from pokerkit: %s", e)
    
    def get_current_player(self, players: Sequence[Player]) -> Optional[Player]:
        """Get the current player who should act"""
        if self._state is None:
            return None
        
        try:
            acting_statuses = self._state.acting_statuses
            for i, is_acting in enumerate(acting_statuses):
                if is_acting and i < len(players):
                    return players[i]
        except AttributeError:
            pass
        
        return None
    
    def process_turn(self, game: Game, players: Sequence[Player]) -> TurnResult:
        """
        Process one turn iteration using pokerkit state.
        
        Returns:
            TurnResult indicating next state
        """
        if self._state is None:
            raise RuntimeError("State not initialized")
        
        # Sync game state from pokerkit
        self.sync_game_from_state(game, players)
        
        # Check if game is finished
        if game.state == GameState.FINISHED:
            return TurnResult.END_GAME
        
        # Count active players
        active_count = sum(
            1 for p in players
            if p.state in (PlayerState.ACTIVE, PlayerState.ALL_IN)
        )
        
        if active_count <= 1:
            logger.info("Only 1 player remains → END_GAME")
            return TurnResult.END_GAME
        
        # Check if betting round is complete using pokerkit
        try:
            acting_statuses = self._state.acting_statuses
            if acting_statuses and not any(acting_statuses):
                # No one is acting - betting round is complete
                logger.info("Betting round complete → END_ROUND")
                return TurnResult.END_ROUND
        except AttributeError:
            # Fallback: check if all bets are matched
            active_players = [p for p in players if p.state == PlayerState.ACTIVE]
            if active_players and game.max_round_rate > 0:
                all_matched = all(
                    p.round_rate == game.max_round_rate for p in active_players
                )
                if all_matched:
                    return TurnResult.END_ROUND
        
        # Check if there's a current player to act
        current_player = self.get_current_player(players)
        if current_player is None:
            # No current player - round might be complete
            return TurnResult.END_ROUND
        
        return TurnResult.CONTINUE_ROUND
    
    def player_action_fold(self) -> None:
        """Player folds"""
        if self._state is None:
            raise RuntimeError("State not initialized")
        
        self._state.fold()
        logger.debug("Player folded")
    
    def player_action_check_or_call(self) -> int:
        """
        Player checks or calls.
        
        Returns:
            Amount of chips committed
        """
        if self._state is None:
            raise RuntimeError("State not initialized")
        
        # Get bet amount before action
        try:
            bet_amounts = self._state.bet_amounts
            current_bet = bet_amounts[self._state.actor_index] if bet_amounts else 0
        except (AttributeError, IndexError):
            current_bet = 0
        
        self._state.check_or_call()
        
        # Get bet amount after action
        try:
            bet_amounts = self._state.bet_amounts
            new_bet = bet_amounts[self._state.actor_index] if bet_amounts else 0
        except (AttributeError, IndexError):
            new_bet = 0
        
        amount_committed = new_bet - current_bet
        logger.debug("Player checked/called: %d chips", amount_committed)
        
        return amount_committed
    
    def player_action_bet_or_raise(self, amount: int) -> int:
        """
        Player bets or raises.
        
        Args:
            amount: Total amount to bet/raise to (not the increment)
        
        Returns:
            Amount of chips committed
        """
        if self._state is None:
            raise RuntimeError("State not initialized")
        
        # Get bet amount before action
        try:
            bet_amounts = self._state.bet_amounts
            current_bet = bet_amounts[self._state.actor_index] if bet_amounts else 0
        except (AttributeError, IndexError):
            current_bet = 0
        
        self._state.complete_bet_or_raise_to(amount)
        
        # Get bet amount after action
        try:
            bet_amounts = self._state.bet_amounts
            new_bet = bet_amounts[self._state.actor_index] if bet_amounts else 0
        except (AttributeError, IndexError):
            new_bet = 0
        
        amount_committed = new_bet - current_bet
        logger.debug("Player bet/raised to %d: %d chips committed", amount, amount_committed)
        
        return amount_committed
    
    def advance_to_next_street(self) -> Tuple[GameState, int]:
        """
        Advance to next betting street.
        This happens automatically in pokerkit when betting round completes.
        
        Returns:
            (new_game_state, cards_to_deal_count)
        """
        if self._state is None:
            raise RuntimeError("State not initialized")
        
        # Get current street
        current_street = self._state.street
        street_name = str(current_street).lower()
        
        # Map to next street and cards to deal
        street_transitions = {
            'deal': (GameState.ROUND_FLOP, 3),  # Pre-flop -> Flop (3 cards)
            'flop': (GameState.ROUND_TURN, 1),   # Flop -> Turn (1 card)
            'turn': (GameState.ROUND_RIVER, 1),  # Turn -> River (1 card)
            'river': (GameState.FINISHED, 0),   # River -> Finished (0 cards)
        }
        
        new_state, cards_count = street_transitions.get(street_name, (GameState.FINISHED, 0))
        
        logger.info(
            "Advancing street: %s -> %s (%d cards to deal)",
            street_name,
            new_state.name,
            cards_count,
        )
        
        return new_state, cards_count
    
    def get_cards_to_deal(self, game_state: GameState) -> int:
        """Get number of community cards to deal for this street"""
        card_counts = {
            GameState.ROUND_PRE_FLOP: 0,
            GameState.ROUND_FLOP: 3,
            GameState.ROUND_TURN: 1,
            GameState.ROUND_RIVER: 1,
            GameState.FINISHED: 0,
        }
        return card_counts.get(game_state, 0)
    
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
    
    def get_pokerkit_state(self) -> Optional[PokerKitState]:
        """Get the underlying pokerkit State (for advanced usage)"""
        return self._state
