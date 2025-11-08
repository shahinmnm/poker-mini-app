#!/usr/bin/env python3

import unittest
from dataclasses import dataclass
from typing import List

from pokerapp.cards import Card
from pokerapp.winnerdetermination import (
    WinnerDetermination,
    get_combination_name,
)


@dataclass
class StubPlayer:
    user_id: int
    cards: List[Card]


class WinnerDeterminationTests(unittest.TestCase):
    def test_detects_straight_flush_winner(self) -> None:
        board = [
            Card("10♠"),
            Card("J♠"),
            Card("K♠"),
            Card("2♣"),
            Card("9♠"),
        ]

        player_one = StubPlayer(
            user_id=1,
            cards=[Card("A♠"), Card("Q♠")],
        )
        player_two = StubPlayer(
            user_id=2,
            cards=[Card("A♦"), Card("K♦")],
        )

        determinator = WinnerDetermination()
        results = determinator.determinate_scores(
            [player_one, player_two],
            board,
        )

        winning_score = max(results.keys())
        winners = results[winning_score]

        self.assertEqual(len(winners), 1)
        self.assertIs(winners[0][0], player_one)
        self.assertEqual(
            get_combination_name(winning_score),
            "Straight flush",
        )

    def test_split_pot_when_hands_match(self) -> None:
        board = [
            Card("A♣"),
            Card("K♦"),
            Card("Q♥"),
            Card("J♣"),
            Card("10♠"),
        ]

        player_one = StubPlayer(1, [Card("9♠"), Card("2♦")])
        player_two = StubPlayer(2, [Card("9♣"), Card("3♣")])

        determinator = WinnerDetermination()
        results = determinator.determinate_scores(
            [player_one, player_two],
            board,
        )

        # All players should share the same straight.
        self.assertEqual(len(results), 1)
        winners = next(iter(results.values()))
        self.assertEqual({winner[0].user_id for winner in winners}, {1, 2})
        score = next(iter(results))
        self.assertEqual(get_combination_name(score), "Straight")

    def test_handles_kicker_strength(self) -> None:
        board = [
            Card("A♠"),
            Card("A♥"),
            Card("K♣"),
            Card("7♦"),
            Card("4♣"),
        ]

        better_pair = StubPlayer(1, [Card("Q♠"), Card("10♦")])
        weaker_pair = StubPlayer(2, [Card("J♠"), Card("10♣")])

        determinator = WinnerDetermination()
        results = determinator.determinate_scores(
            [better_pair, weaker_pair],
            board,
        )

        winning_score = max(results.keys())
        winners = results[winning_score]

        self.assertEqual(len(winners), 1)
        self.assertIs(winners[0][0], better_pair)
        self.assertEqual(get_combination_name(winning_score), "One pair")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
