#!/usr/bin/env python3

from typing import List

from pokerapp.pokerkit_adapter import generate_shuffled_unicode_deck

class Card(str):
    @property
    def suit(self) -> str:
        return self[-1:]

    @property
    def rank(self) -> str:
        return self[:-1]

    @property
    def value(self) -> str:
        if self[0] == "J":
            return 11
        elif self[0] == "Q":
            return 12
        elif self[0] == "K":
            return 13
        elif self[0] == "A":
            return 14
        return int(self[:-1])


Cards = List[Card]


def get_cards() -> Cards:
    return [Card(text) for text in generate_shuffled_unicode_deck()]


def get_shuffled_deck() -> Cards:
    """Return a freshly shuffled deck of cards."""

    return get_cards()
