"""
shared.models — модели данных проекта "Миллиардер".

Содержит dataclass-модели, представляющие все сущности игры:
- User, PlayerProfile (user.py)
- Property, PropertyState, PropertyGroup (property.py)
- Card, PlayerCard, CardDeck (card.py)
- CellPosition, BoardPosition, Board (position.py)
- GameEvent, DiceRolledData, PropertyBoughtData, ... (event.py)
- TradeOffer, TradeResult (trade.py)
- Room, RoomConfig, RoomListItem (room.py)
- Game, PlayerState, GameConfig, GameResult (game.py)

Все модели используют @dataclass(slots=True), UUID для идентификаторов,
и предоставляют методы to_dict()/from_dict() для сериализации.

Python: 3.13+
"""