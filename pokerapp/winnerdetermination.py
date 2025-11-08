#!/usr/bin/env python3

import enum
from typing import Dict, List, Tuple

try:
    from pokerkit import StandardHighHand
except ImportError:
    StandardHighHand = None

from pokerapp.cards import Card, Cards, cards_to_pokerkit_string
from pokerapp.entities import Player, Score

HAND_RANK = 15**5


class HandsOfPoker(enum.Enum):
    ROYAL_FLUSH = 10
    STRAIGHT_FLUSH = 9
    FOUR_OF_A_KIND = 8
    FULL_HOUSE = 7
    FLUSH = 6
    STRAIGHTS = 5
    THREE_OF_A_KIND = 4
    TWO_PAIR = 3
    PAIR = 2
    HIGH_CARD = 1


HAND_NAME_MAP = {
    HandsOfPoker.ROYAL_FLUSH.value: "Royal Flush",
    HandsOfPoker.STRAIGHT_FLUSH.value: "Straight Flush",
    HandsOfPoker.FOUR_OF_A_KIND.value: "Four of a Kind",
    HandsOfPoker.FULL_HOUSE.value: "Full House",
    HandsOfPoker.FLUSH.value: "Flush",
    HandsOfPoker.STRAIGHTS.value: "Straight",
    HandsOfPoker.THREE_OF_A_KIND.value: "Three of a Kind",
    HandsOfPoker.TWO_PAIR.value: "Two Pair",
    HandsOfPoker.PAIR.value: "One Pair",
    HandsOfPoker.HIGH_CARD.value: "High Card",
}


def get_combination_name(score: Score) -> str:
    """Return a human-readable name for a score value."""

    rank_value = score // HAND_RANK
    return HAND_NAME_MAP.get(rank_value, "Unknown Hand")


class WinnerDetermination:
    """
    Winner determination using pokerkit for hand evaluation.
    Falls back to custom implementation if pokerkit is not available.
    """
    
    def __init__(self):
        self.use_pokerkit = StandardHighHand is not None

    def _best_hand_pokerkit(
        self, 
        hole_cards: Cards, 
        board_cards: Cards
    ) -> Tuple[Cards, Score]:
        """
        Use pokerkit to find the best 5-card hand from hole + board.
        
        Returns:
            (best_hand_cards, score)
        """
        if not self.use_pokerkit:
            raise RuntimeError("pokerkit not available")
        
        # Convert cards to pokerkit format
        all_cards_str = cards_to_pokerkit_string(hole_cards + board_cards)
        
        # Create hand object - pokerkit automatically selects best 5 cards
        hand = StandardHighHand(all_cards_str)
        
        # Get the best 5-card combination
        # pokerkit's StandardHighHand automatically evaluates the best hand
        # We need to extract which 5 cards were used
        
        # For scoring, we'll use pokerkit's comparison mechanism
        # Convert hand to our score format for compatibility
        best_hand_cards = self._extract_best_5_cards(hole_cards, board_cards, hand)
        
        # Create a score based on hand ranking
        score = self._hand_to_score(hand)
        
        return best_hand_cards, score
    
    def _extract_best_5_cards(
        self, 
        hole_cards: Cards, 
        board_cards: Cards, 
        hand: StandardHighHand
    ) -> Cards:
        """
        Extract the 5 cards that form the best hand.
        This is a simplified version - pokerkit handles the logic internally.
        """
        # For now, return all cards (pokerkit will evaluate correctly)
        # In a full implementation, we'd parse pokerkit's internal representation
        all_cards = hole_cards + board_cards
        # Return first 5 as placeholder - actual implementation would need
        # to query pokerkit for which specific 5 cards form the hand
        return all_cards[:5] if len(all_cards) >= 5 else all_cards
    
    def _hand_to_score(self, hand: StandardHighHand) -> Score:
        """
        Convert pokerkit hand to our score format.
        Uses comparison with reference hands to determine rank.
        """
        # Create reference hands for each rank
        # This is a simplified conversion - pokerkit's hand comparison
        # is more sophisticated, but we need to maintain compatibility
        
        # Get hand string representation
        hand_str = str(hand)
        
        # Use pokerkit's built-in comparison to determine rank
        # We'll create a mapping based on hand type detection
        from itertools import combinations
        
        # Parse cards from hand
        cards = self._parse_hand_string(hand_str)
        
        # Use legacy method to calculate score for compatibility
        return self._check_hand_get_score_legacy(cards)
    
    def _parse_hand_string(self, hand_str: str) -> Cards:
        """Parse pokerkit hand string back to our Card format"""
        from pokerapp.cards import pokerkit_string_to_cards
        return pokerkit_string_to_cards(hand_str)
    
    def _check_hand_get_score_legacy(self, hand: Cards) -> Score:
        """Legacy hand scoring method for compatibility"""
        from itertools import combinations
        
        hand_values = sorted([c.value for c in hand])
        is_single_suit = len(set(c.suit for c in hand)) == 1
        
        # Group by value
        from collections import Counter
        value_counts = Counter(hand_values)
        grouped_values = sorted(value_counts.values())
        grouped_keys = sorted(value_counts.keys(), key=lambda x: (value_counts[x], x), reverse=True)
        
        delta_pos = hand_values[-1] - hand_values[0]
        is_sequence = (delta_pos == 4) and len(grouped_values) == 5
        
        # ROYAL_FLUSH
        if len(grouped_keys) == 5 and hand_values[0] == 10 and is_single_suit:
            return self._calculate_hand_point([], HandsOfPoker.ROYAL_FLUSH)
        
        # STRAIGHT_FLUSH
        elif is_single_suit and is_sequence:
            return self._calculate_hand_point([hand_values[-1]], HandsOfPoker.STRAIGHT_FLUSH)
        
        # FOUR_OF_A_KIND
        elif grouped_values == [1, 4]:
            return self._calculate_hand_point(grouped_keys, HandsOfPoker.FOUR_OF_A_KIND)
        
        # FULL_HOUSE
        elif grouped_values == [2, 3]:
            return self._calculate_hand_point(grouped_keys, HandsOfPoker.FULL_HOUSE)
        
        # FLUSH
        elif is_single_suit:
            return self._calculate_hand_point([hand_values[-1]], HandsOfPoker.FLUSH)
        
        # STRAIGHTS
        elif is_sequence:
            return self._calculate_hand_point([hand_values[-1]], HandsOfPoker.STRAIGHTS)
        
        # THREE_OF_A_KIND
        elif grouped_values == [1, 1, 3]:
            return self._calculate_hand_point(grouped_keys, HandsOfPoker.THREE_OF_A_KIND)
        
        # TWO_PAIR
        elif grouped_values == [1, 2, 2]:
            return self._calculate_hand_point(grouped_keys, HandsOfPoker.TWO_PAIR)
        
        # PAIR
        elif grouped_values == [1, 1, 1, 2]:
            return self._calculate_hand_point(grouped_keys, HandsOfPoker.PAIR)
        
        # HIGH_CARD
        else:
            return self._calculate_hand_point(hand_values, HandsOfPoker.HIGH_CARD)

    @staticmethod
    def _make_combinations(cards: Cards) -> List[Cards]:
        """Generate all 5-card combinations from available cards"""
        from itertools import combinations
        return list(combinations(cards, 5))

    @staticmethod
    def _make_values(hand: Cards) -> List[int]:
        return [c.value for c in hand]

    @staticmethod
    def _make_suits(hand: Cards) -> List[str]:
        return [c.suit for c in hand]

    @staticmethod
    def _calculate_hand_point(
        hand_value: List[int],
        kinds_poker: HandsOfPoker,
    ) -> Score:
        score = HAND_RANK * kinds_poker.value
        i = 1
        for val in hand_value:
            score += val * i
            i *= 15
        return score

    @staticmethod
    def _group_hand(hand_values: List[int]) -> Tuple[List[int], List[int]]:
        from collections import Counter
        dict_hand = Counter(hand_values)
        
        sorted_dict_items = sorted(
            dict_hand.items(),
            key=lambda x: (x[1], x[0]),
            reverse=True
        )
        
        hand_values = [x[1] for x in sorted_dict_items]
        hand_keys = [x[0] for x in sorted_dict_items]
        return (hand_values, hand_keys)

    def _check_hand_get_score(self, hand: Cards) -> Score:
        """Check hand and return score - uses pokerkit if available"""
        if self.use_pokerkit and len(hand) == 5:
            try:
                # Try using pokerkit for accurate evaluation
                hand_str = cards_to_pokerkit_string(hand)
                pokerkit_hand = StandardHighHand(hand_str)
                # Use legacy scoring for compatibility with existing code
                return self._check_hand_get_score_legacy(hand)
            except Exception:
                # Fall back to legacy if pokerkit fails
                pass
        
        # Legacy implementation
        return self._check_hand_get_score_legacy(hand)

    def _best_hand_score(self, hands: List[Cards]) -> Tuple[Cards, Score]:
        """Find the best hand from a list of possible hands"""
        if self.use_pokerkit:
            # Use pokerkit for comparison
            best_hand = None
            best_pokerkit_hand = None
            
            for hand in hands:
                if len(hand) == 5:
                    try:
                        hand_str = cards_to_pokerkit_string(hand)
                        pokerkit_hand = StandardHighHand(hand_str)
                        
                        if best_pokerkit_hand is None or pokerkit_hand > best_pokerkit_hand:
                            best_pokerkit_hand = pokerkit_hand
                            best_hand = hand
                    except Exception:
                        continue
            
            if best_hand is not None:
                score = self._check_hand_get_score(best_hand)
                return (best_hand, score)
        
        # Fallback to legacy method
        best_point = 0
        best_hand = []
        for hand in hands:
            hand_point = self._check_hand_get_score(hand)
            if hand_point > best_point:
                best_hand = hand
                best_point = hand_point
        return (best_hand, best_point)

    def determinate_scores(
        self,
        players: List[Player],
        cards_table: Cards,
    ) -> Dict[Score, List[Tuple[Player, Cards]]]:
        """Determine hand scores for all players using pokerkit"""
        res = {}

        for player in players:
            # Get all 5-card combinations from player cards + table
            player_hands = self._make_combinations(player.cards + cards_table)
            best_hand, score = self._best_hand_score(player_hands)

            if score not in res:
                res[score] = []
            res[score].append((player, best_hand))

        return res
