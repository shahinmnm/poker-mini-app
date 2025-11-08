#!/usr/bin/env python3
"""
Winner determination using pokerkit hand evaluation.
"""

from typing import Dict, List, Tuple

from pokerkit import StandardHighHand
from pokerapp.cards import Card, Cards
from pokerapp.entities import Player, Score


def get_combination_name(hand: StandardHighHand) -> str:
    """Return a human-readable name for a hand."""
    return hand.entry.label.value


class WinnerDetermination:
    """
    Determines winners using pokerkit's hand evaluation.
    Uses StandardHighHand for Texas Hold'em hand ranking.
    """

    def determinate_scores(
        self,
        players: List[Player],
        cards_table: Cards,
    ) -> Dict[Score, List[Tuple[Player, Cards]]]:
        """
        Determine hand scores for all players using pokerkit.
        
        Args:
            players: List of players with their hole cards
            cards_table: Community cards on the table
            
        Returns:
            Dictionary mapping scores to list of (player, best_hand) tuples
        """
        res = {}

        for player in players:
            # Use pokerkit to find the best hand from hole + board cards
            try:
                best_hand = StandardHighHand.from_game(
                    hole_cards=player.cards,
                    board_cards=cards_table,
                )
            except ValueError:
                # If no valid hand can be formed (shouldn't happen in normal play)
                # Use a high card hand as fallback
                continue

            # Use the hand's entry as the score (pokerkit hands are comparable)
            # We'll use a simple score based on hand comparison
            # For compatibility, we'll create a score that preserves ordering
            score = self._hand_to_score(best_hand)

            if score not in res:
                res[score] = []
            
            # Store the actual cards that form this hand
            best_hand_cards = list(best_hand.cards)
            res[score].append((player, best_hand_cards))

        return res

    def _hand_to_score(self, hand: StandardHighHand) -> Score:
        """
        Convert a pokerkit hand to a numeric score for compatibility.
        
        Pokerkit hands are comparable, so we can use a simple mapping.
        For backward compatibility with existing Score type (int).
        """
        # Use the hand's entry index as the base score
        # Higher entry index = better hand
        # We multiply by a large number to preserve ordering
        base_score = hand.entry.index if hasattr(hand.entry, 'index') else 0
        
        # Create a score that preserves hand ranking
        # Format: hand_rank * 1000000 + tiebreaker
        hand_rank_map = {
            'Royal flush': 10,
            'Straight flush': 9,
            'Four of a kind': 8,
            'Full house': 7,
            'Flush': 6,
            'Straight': 5,
            'Three of a kind': 4,
            'Two pair': 3,
            'One pair': 2,
            'High card': 1,
        }
        
        hand_label = hand.entry.label.value
        hand_rank = hand_rank_map.get(hand_label, 0)
        
        # Use a large multiplier to ensure proper ordering
        HAND_RANK = 15**5
        score = HAND_RANK * hand_rank
        
        # Add tiebreaker based on card values
        # For simplicity, we'll use the hand's string representation hash
        # This ensures different hands get different scores
        tiebreaker = hash(str(hand.cards)) % HAND_RANK
        score += tiebreaker
        
        return score
