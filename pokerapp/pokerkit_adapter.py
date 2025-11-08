#!/usr/bin/env python3
"""
Utilities for converting between the project's traditional card
representation and PokerKit's card model.

This module centralises the translation logic so the rest of the codebase
can work with human-friendly strings (e.g. ``"A♠"`` or ``"10♥"``) while the
game core leverages the rich primitives offered by the ``pokerkit``
library.

The helpers provided here intentionally avoid any Telegram/UI concerns –
they exist purely to make interacting with PokerKit easier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pokerkit.utilities import Card as PKCard
from pokerkit.utilities import Deck, Rank, Suit, shuffled


# ---------------------------------------------------------------------------
# Suit and rank conversion tables
# ---------------------------------------------------------------------------

_POKERKIT_SUIT_TO_UNICODE = {
    "c": "♣",
    "d": "♦",
    "h": "♥",
    "s": "♠",
}

_UNICODE_TO_POKERKIT_SUIT = {
    symbol: code for code, symbol in _POKERKIT_SUIT_TO_UNICODE.items()
}

# Telegram/Unicode fonts sometimes include a variation selector (e.g. "♠️").
# Normalise those to the plain suit glyph so downstream code has a single
# canonical representation to work with.
_VARIATION_SELECTORS = {
    "♠️": "♠",
    "♥️": "♥",
    "♦️": "♦",
    "♣️": "♣",
    "♤": "♠",
    "♡": "♥",
    "♢": "♦",
    "♧": "♣",
}

_POKERKIT_RANK_TO_TEXT = {
    "A": "A",
    "K": "K",
    "Q": "Q",
    "J": "J",
    "T": "10",
    "9": "9",
    "8": "8",
    "7": "7",
    "6": "6",
    "5": "5",
    "4": "4",
    "3": "3",
    "2": "2",
}

_TEXT_TO_POKERKIT_RANK = {
    text: code for code, text in _POKERKIT_RANK_TO_TEXT.items()
}


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _normalise_suit_symbol(symbol: str) -> str:
    """Return a canonical single-glyph suit symbol."""

    if symbol in _VARIATION_SELECTORS:
        return _VARIATION_SELECTORS[symbol]

    return symbol


def _split_card_text(card: str) -> tuple[str, str]:
    """
    Split a human readable card string into ``(rank, suit)`` tokens.

    Examples::

        "A♠"  -> ("A", "♠")
        "10♥" -> ("10", "♥")
    """

    text = card.strip()
    if not text:
        raise ValueError("Card text cannot be empty")

    suit_symbol = _normalise_suit_symbol(text[-1])
    rank_text = text[:-1].upper()

    if suit_symbol not in _UNICODE_TO_POKERKIT_SUIT:
        raise ValueError(f"Unsupported suit symbol: {suit_symbol!r}")

    if rank_text not in _TEXT_TO_POKERKIT_RANK:
        raise ValueError(f"Unsupported rank text: {rank_text!r}")

    return rank_text, suit_symbol


def unicode_to_pk_card(card: str) -> PKCard:
    """Convert a string like ``\"A♠\"`` into a PokerKit :class:`Card`."""

    rank_text, suit_symbol = _split_card_text(card)

    rank = Rank(_TEXT_TO_POKERKIT_RANK[rank_text])
    suit = Suit(_UNICODE_TO_POKERKIT_SUIT[suit_symbol])

    return PKCard(rank, suit)


def unicode_to_pk_cards(cards: Iterable[str]) -> tuple[PKCard, ...]:
    """Convert an iterable of unicode cards to PokerKit cards."""

    return tuple(unicode_to_pk_card(card) for card in cards)


def pk_card_to_unicode(card: PKCard) -> str:
    """Convert a PokerKit :class:`Card` into a string like ``\"A♠\"``."""

    rank_token = card.rank.value
    suit_token = card.suit.value

    if rank_token not in _POKERKIT_RANK_TO_TEXT:
        raise ValueError(f"Unsupported PokerKit rank token: {rank_token!r}")

    if suit_token not in _POKERKIT_SUIT_TO_UNICODE:
        raise ValueError(f"Unsupported PokerKit suit token: {suit_token!r}")

    rank_text = _POKERKIT_RANK_TO_TEXT[rank_token]
    suit_symbol = _POKERKIT_SUIT_TO_UNICODE[suit_token]

    return f"{rank_text}{suit_symbol}"


def pk_cards_to_unicode(cards: Iterable[PKCard]) -> list[str]:
    """Convert PokerKit cards into unicode strings."""

    return [pk_card_to_unicode(card) for card in cards]


def unicode_cards_to_compact(cards: Iterable[str]) -> str:
    """
    Convert unicode card strings into PokerKit's compact text format.

    ``(\"A♠\", \"10♥\")`` becomes ``\"AsTh\"``.
    """

    compact_tokens: list[str] = []

    for card in cards:
        rank_text, suit_symbol = _split_card_text(card)
        compact_tokens.append(_TEXT_TO_POKERKIT_RANK[rank_text])
        compact_tokens.append(_UNICODE_TO_POKERKIT_SUIT[suit_symbol])

    return "".join(compact_tokens)


def pk_cards_to_compact(cards: Iterable[PKCard]) -> str:
    """Return a PokerKit compact string (e.g. ``\"AsTh\"``)."""

    return "".join(card.rank.value + card.suit.value for card in cards)


# ---------------------------------------------------------------------------
# Deck helpers
# ---------------------------------------------------------------------------

def generate_shuffled_unicode_deck() -> list[str]:
    """
    Return a freshly shuffled deck represented with unicode suit glyphs.

    The deck contents are produced via PokerKit's deck utilities to keep
    the application aligned with the library's canonical card ordering.
    """

    pk_cards = shuffled(Deck.STANDARD)
    return pk_cards_to_unicode(pk_cards)


# ---------------------------------------------------------------------------
# Data containers (optional but handy for type hints)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PokerKitHand:
    """
    Lightweight value object holding the hole and board cards associated
    with a PokerKit-evaluated hand.
    """

    cards: tuple[PKCard, ...]

    def as_unicode(self) -> list[str]:
        return pk_cards_to_unicode(self.cards)

    def as_compact(self) -> str:
        return pk_cards_to_compact(self.cards)

