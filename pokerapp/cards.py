#!/usr/bin/env python3

import random
from typing import List

try:
    from pokerkit import Card as PokerKitCard, Deck
except ImportError:
    # Fallback if pokerkit is not installed
    PokerKitCard = None
    Deck = None


class Card(str):
    """
    Card representation compatible with both our format and pokerkit.
    Our format: "2♥", "A♠", "10♣"
    PokerKit format: "2h", "As", "Tc"
    """
    
    # Mapping from our suit symbols to pokerkit suit letters
    SUIT_MAP = {
        '♥': 'h',  # hearts
        '♦': 'd',  # diamonds
        '♣': 'c',  # clubs
        '♠': 's',  # spades
    }
    
    # Reverse mapping
    SUIT_REVERSE_MAP = {v: k for k, v in SUIT_MAP.items()}
    
    # Rank mapping
    RANK_MAP = {
        'J': 'J',
        'Q': 'Q',
        'K': 'K',
        'A': 'A',
    }

    @property
    def suit(self) -> str:
        """Return suit symbol (♥, ♦, ♣, ♠)"""
        return self[-1:]

    @property
    def rank(self) -> str:
        """Return rank string (2-10, J, Q, K, A)"""
        return self[:-1]

    @property
    def value(self) -> int:
        """Return numeric value for comparison"""
        rank = self.rank
        if rank == "J":
            return 11
        elif rank == "Q":
            return 12
        elif rank == "K":
            return 13
        elif rank == "A":
            return 14
        return int(rank)

    def to_pokerkit(self) -> str:
        """Convert to pokerkit notation (e.g., '2h', 'As')"""
        if PokerKitCard is None:
            raise ImportError("pokerkit not installed")
        
        rank = self.rank
        suit_symbol = self.suit
        suit_letter = self.SUIT_MAP.get(suit_symbol, suit_symbol.lower())
        
        # Convert rank: 10 -> T, others stay the same
        if rank == "10":
            rank = "T"
        
        return f"{rank}{suit_letter}"

    @classmethod
    def from_pokerkit(cls, pokerkit_card: str) -> 'Card':
        """Create Card from pokerkit notation (e.g., '2h', 'As')"""
        if len(pokerkit_card) < 2:
            raise ValueError(f"Invalid pokerkit card: {pokerkit_card}")
        
        rank = pokerkit_card[:-1]
        suit_letter = pokerkit_card[-1]
        
        # Convert T back to 10
        if rank == "T":
            rank = "10"
        
        suit_symbol = cls.SUIT_REVERSE_MAP.get(suit_letter, suit_letter)
        
        return cls(f"{rank}{suit_symbol}")


Cards = List[Card]


def get_cards() -> Cards:
    """Generate a standard 52-card deck"""
    cards = [
        Card("2♥"), Card("3♥"), Card("4♥"), Card("5♥"),
        Card("6♥"), Card("7♥"), Card("8♥"), Card("9♥"),
        Card("10♥"), Card("J♥"), Card("Q♥"), Card("K♥"),
        Card("A♥"), Card("2♦"), Card("3♦"), Card("4♦"),
        Card("5♦"), Card("6♦"), Card("7♦"), Card("8♦"),
        Card("9♦"), Card("10♦"), Card("J♦"), Card("Q♦"),
        Card("K♦"), Card("A♦"), Card("2♣"), Card("3♣"),
        Card("4♣"), Card("5♣"), Card("6♣"), Card("7♣"),
        Card("8♣"), Card("9♣"), Card("10♣"), Card("J♣"),
        Card("Q♣"), Card("K♣"), Card("A♣"), Card("2♠"),
        Card("3♠"), Card("4♠"), Card("5♠"), Card("6♠"),
        Card("7♠"), Card("8♠"), Card("9♠"), Card("10♠"),
        Card("J♠"), Card("Q♠"), Card("K♠"), Card("A♠"),
    ]
    random.SystemRandom().shuffle(cards)
    return cards


def get_shuffled_deck() -> Cards:
    """Return a freshly shuffled deck of cards."""
    return get_cards()


def cards_to_pokerkit_string(cards: Cards) -> str:
    """Convert a list of Cards to pokerkit string format"""
    return ''.join(card.to_pokerkit() for card in cards)


def pokerkit_string_to_cards(pokerkit_string: str) -> Cards:
    """Convert pokerkit string format to list of Cards"""
    cards = []
    i = 0
    while i < len(pokerkit_string):
        # Cards are 2 characters: rank + suit
        if i + 2 <= len(pokerkit_string):
            card_str = pokerkit_string[i:i+2]
            cards.append(Card.from_pokerkit(card_str))
            i += 2
        else:
            break
    return cards
