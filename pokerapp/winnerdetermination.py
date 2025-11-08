#!/usr/bin/env python3

from typing import Dict, List, Tuple

from pokerkit.hands import StandardHighHand

from pokerapp.cards import Cards
from pokerapp.entities import Player, Score
from pokerapp.pokerkit_adapter import (
    pk_cards_to_unicode,
    unicode_to_pk_cards,
)

_HAND_LABELS: Dict[Score, str] = {}


def get_combination_name(score: Score) -> str:
    """Return a human-readable name for a score value."""

    return _HAND_LABELS.get(score, "Unknown Hand")


class WinnerDetermination:
    def determinate_scores(
        self,
        players: List[Player],
        cards_table: Cards,
    ) -> Dict[Score, List[Tuple[Player, Cards]]]:
        """
        Evaluate the players' hands using PokerKit's standard hold'em
        evaluator.
        """

        board_cards = unicode_to_pk_cards(cards_table)
        results: Dict[Score, List[Tuple[Player, Cards]]] = {}

        for player in players:
            hole_cards = unicode_to_pk_cards(player.cards)
            best_hand = StandardHighHand.from_game(hole_cards, board_cards)
            score: Score = best_hand.entry.index
            _HAND_LABELS[score] = best_hand.entry.label.value

            results.setdefault(score, []).append(
                (player, pk_cards_to_unicode(best_hand.cards)),
            )

        return results
