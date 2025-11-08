#!/usr/bin/env python3
"""
Card utilities using pokerkit library.
Provides compatibility layer for existing card format (Unicode suits).
"""

from typing import List
from pokerkit import Card as PokerKitCard, Deck as PokerKitDeck, shuffled


# Type alias for backward compatibility
Card = PokerKitCard
Cards = List[Card]


def _convert_to_pokerkit_format(card_str: str) -> str:
    """
    Convert from Unicode suit format (2♥, 10♥, J♥) to pokerkit format (2h, Th, Jh).
    
    Args:
        card_str: Card string in format like "2♥", "10♥", "J♥", "A♠"
        
    Returns:
        Card string in pokerkit format like "2h", "Th", "Jh", "As"
    """
    suit_map = {
        '♥': 'h',  # hearts
        '♦': 'd',  # diamonds
        '♣': 'c',  # clubs
        '♠': 's',  # spades
    }
    
    rank_map = {
        '10': 'T',
    }
    
    # Extract suit (last character)
    suit_char = card_str[-1]
    suit = suit_map.get(suit_char, suit_char.lower())
    
    # Extract rank (everything except last character)
    rank = card_str[:-1]
    rank = rank_map.get(rank, rank)
    
    return rank + suit


def _convert_from_pokerkit_format(card: PokerKitCard) -> str:
    """
    Convert from pokerkit format to Unicode suit format for display.
    
    Args:
        card: PokerKit Card object
        
    Returns:
        Card string in Unicode format like "2♥", "T♥", "J♥", "A♠"
    """
    suit_map = {
        'h': '♥',  # hearts
        'd': '♦',  # diamonds
        'c': '♣',  # clubs
        's': '♠',  # spades
    }
    
    rank_map = {
        'T': '10',
    }
    
    # Get rank and suit from pokerkit card
    rank = str(card.rank.value)
    suit = card.suit.value
    
    # Convert rank if needed
    rank = rank_map.get(rank, rank)
    
    # Convert suit
    suit_unicode = suit_map.get(suit, suit)
    
    return rank + suit_unicode


def get_cards() -> Cards:
    """
    Get a shuffled deck of cards using pokerkit.
    Returns cards in pokerkit format (compatible with existing code).
    """
    deck = shuffled(PokerKitDeck.STANDARD)
    return list(deck)


def get_shuffled_deck() -> Cards:
    """Return a freshly shuffled deck of cards."""
    return get_cards()
