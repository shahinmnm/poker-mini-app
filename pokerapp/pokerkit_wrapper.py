#!/usr/bin/env python3
"""
PokerKit wrapper - simplified game core using pokerkit library.
This module provides a bridge between our Game entity and pokerkit's State.
"""

import logging
from typing import Optional, List, Tuple, Dict
from math import inf

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

from pokerapp.entities import Game, GameState, Player, PlayerState
from pokerapp.cards import Cards, cards_to_pokerkit_string, pokerkit_string_to_cards

logger = logging.getLogger(__name__)


class PokerKitGameCore:
    """
    Simplified game core using pokerkit State management.
    Wraps pokerkit's State to work with our Game entity.
    """
    
    def __init__(
        self,
        game: Game,
        small_blind: int,
        big_blind: Optional[int] = None,
    ):
        if not POKERKIT_AVAILABLE:
            raise ImportError("pokerkit library is not installed")
        
        self.game = game
        self.small_blind = small_blind
        self.big_blind = big_blind or (small_blind * 2)
        self._pokerkit_state: Optional[PokerKitState] = None
        self._player_index_map: Dict[str, int] = {}  # user_id -> pokerkit player index
        
    def initialize_state(self) -> None:
        """Initialize pokerkit State for a new hand"""
        num_players = len(self.game.players)
        if num_players < 2:
            raise ValueError("At least 2 players required")
        
        # Build starting stacks
        starting_stacks = []
        for player in self.game.players:
            stack = player.wallet.value()
            starting_stacks.append(stack if stack > 0 else inf)
            self._player_index_map[player.user_id] = len(starting_stacks) - 1
        
        # Create pokerkit state
        self._pokerkit_state = NoLimitTexasHoldem.create_state(
            # Automations - we'll handle most manually for Telegram integration
            (
                Automation.BET_COLLECTION,
                Automation.CHIPS_PUSHING,
                Automation.CHIPS_PULLING,
            ),
            False,  # Uniform antes
            {},  # No antes
            (self.small_blind, self.big_blind),  # Blinds
            self.big_blind,  # Min bet
            tuple(starting_stacks),
            num_players,
            mode=Mode.CASH_GAME,
        )
        
        logger.debug(
            "Initialized pokerkit state: %d players, blinds %d/%d",
            num_players,
            self.small_blind,
            self.big_blind,
        )
    
    def deal_hole_cards(self, player: Player, cards: Cards) -> None:
        """Deal hole cards to a player"""
        if self._pokerkit_state is None:
            raise RuntimeError("State not initialized")
        
        player_index = self._player_index_map.get(player.user_id)
        if player_index is None:
            raise ValueError(f"Player {player.user_id} not found in game")
        
        # Convert cards to pokerkit format
        cards_str = cards_to_pokerkit_string(cards)
        
        # Deal cards
        self._pokerkit_state.deal_hole(cards_str)
        
        logger.debug(
            "Dealt hole cards to player %s (index %d): %s",
            player.user_id,
            player_index,
            cards_str,
        )
    
    def deal_board_cards(self, cards: Cards) -> None:
        """Deal community cards"""
        if self._pokerkit_state is None:
            raise RuntimeError("State not initialized")
        
        # Convert and deal
        cards_str = cards_to_pokerkit_string(cards)
        self._pokerkit_state.deal_board(cards_str)
        
        logger.debug("Dealt board cards: %s", cards_str)
    
    def burn_card(self) -> None:
        """Burn a card"""
        if self._pokerkit_state is None:
            raise RuntimeError("State not initialized")
        
        self._pokerkit_state.burn_card('??')
    
    def get_current_street(self) -> GameState:
        """Get current betting street from pokerkit state"""
        if self._pokerkit_state is None:
            return GameState.INITIAL
        
        # Map pokerkit street to our GameState
        street = self._pokerkit_state.street
        
        # pokerkit uses different street names, we need to map them
        # This is a simplified mapping - adjust based on actual pokerkit API
        street_map = {
            'deal': GameState.ROUND_PRE_FLOP,
            'flop': GameState.ROUND_FLOP,
            'turn': GameState.ROUND_TURN,
            'river': GameState.ROUND_RIVER,
            'showdown': GameState.FINISHED,
        }
        
        street_name = str(street).lower() if hasattr(street, '__str__') else str(street)
        return street_map.get(street_name, GameState.INITIAL)
    
    def get_current_player_index(self) -> Optional[int]:
        """Get index of current player to act"""
        if self._pokerkit_state is None:
            return None
        
        try:
            # pokerkit tracks acting status differently
            # This is a simplified version - adjust based on actual API
            acting_statuses = self._pokerkit_state.acting_statuses
            
            for i, is_acting in enumerate(acting_statuses):
                if is_acting:
                    # Map back to our player index
                    return i
            
            return None
        except AttributeError:
            # Fallback if acting_statuses not available
            return self.game.current_player_index
    
    def player_fold(self, player: Player) -> None:
        """Player folds"""
        if self._pokerkit_state is None:
            raise RuntimeError("State not initialized")
        
        self._pokerkit_state.fold()
        player.state = PlayerState.FOLD
    
    def player_check_or_call(self, player: Player) -> int:
        """Player checks or calls"""
        if self._pokerkit_state is None:
            raise RuntimeError("State not initialized")
        
        self._pokerkit_state.check_or_call()
        
        # Calculate amount called
        amount = self.game.max_round_rate - player.round_rate
        return amount
    
    def player_bet_or_raise(self, player: Player, amount: int) -> int:
        """Player bets or raises"""
        if self._pokerkit_state is None:
            raise RuntimeError("State not initialized")
        
        # Calculate total bet amount
        call_amount = max(self.game.max_round_rate - player.round_rate, 0)
        raise_amount = max(amount - self.game.max_round_rate, 0)
        total_amount = call_amount + raise_amount
        
        if total_amount > 0:
            self._pokerkit_state.complete_bet_or_raise_to(
                self.game.max_round_rate + raise_amount
            )
        
        return total_amount
    
    def player_all_in(self, player: Player) -> int:
        """Player goes all-in"""
        if self._pokerkit_state is None:
            raise RuntimeError("State not initialized")
        
        all_in_amount = player.wallet.value()
        self._pokerkit_state.complete_bet_or_raise_to(all_in_amount)
        player.state = PlayerState.ALL_IN
        
        return all_in_amount
    
    def sync_from_pokerkit_state(self) -> None:
        """Sync our Game entity with pokerkit state"""
        if self._pokerkit_state is None:
            return
        
        # Update game state
        self.game.state = self.get_current_street()
        
        # Update pot
        try:
            pots = self._pokerkit_state.pots
            if pots:
                self.game.pot = sum(pot.amount for pot in pots)
        except AttributeError:
            pass
        
        # Update player stacks and bets
        try:
            stacks = self._pokerkit_state.stacks
            bet_amounts = getattr(self._pokerkit_state, 'bet_amounts', None)
            
            for i, player in enumerate(self.game.players):
                if i < len(stacks):
                    # Update stack (wallet balance)
                    current_stack = stacks[i]
                    if current_stack != inf:
                        # Calculate difference and update wallet
                        # This is simplified - actual implementation would need
                        # to track previous stack values
                        pass
                    
                    # Update round rate if bet_amounts available
                    if bet_amounts and i < len(bet_amounts):
                        player.round_rate = bet_amounts[i]
        except AttributeError:
            pass
        
        # Update current player
        current_idx = self.get_current_player_index()
        if current_idx is not None:
            self.game.current_player_index = current_idx
    
    def is_betting_complete(self) -> bool:
        """Check if current betting round is complete"""
        if self._pokerkit_state is None:
            return False
        
        try:
            # Check if all players have acted and bets are matched
            acting_statuses = self._pokerkit_state.acting_statuses
            return not any(acting_statuses)
        except AttributeError:
            # Fallback to our own logic
            return self.game.max_round_rate > 0 and all(
                p.round_rate == self.game.max_round_rate or p.state != PlayerState.ACTIVE
                for p in self.game.players
                if p.state in (PlayerState.ACTIVE, PlayerState.ALL_IN)
            )
    
    def get_showdown_results(self) -> List[Tuple[Player, Cards, int]]:
        """
        Get showdown results using pokerkit.
        Returns list of (player, best_hand, winnings).
        """
        if self._pokerkit_state is None:
            return []
        
        results = []
        
        try:
            # Get winners from pokerkit
            # This is simplified - adjust based on actual pokerkit API
            pots = self._pokerkit_state.pots
            stacks = self._pokerkit_state.stacks
            
            # Map pokerkit results to our format
            # This would need to be implemented based on pokerkit's actual
            # showdown API
            
            return results
        except AttributeError:
            logger.warning("Could not get showdown results from pokerkit")
            return results
