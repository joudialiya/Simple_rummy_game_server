from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped, Relationship, Session
from sqlalchemy import create_engine, String, ForeignKey
from typing import List, Literal, Dict
class Base(DeclarativeBase):
  pass

class Player(Base):
  __tablename__ = "players"

  id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
  name: Mapped[String] = mapped_column(String)

class Card(Base):
  __tablename__ = "cards"

  id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
  symbol: Mapped[Literal["Piques", "Cœurs", "Carreaux", "Trèfles"]] = mapped_column(String)
  number: Mapped[int] = mapped_column()

class Party(Base):
  __tablename__ = "parties"

  id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

class PartyPlayerHand(Base):
  __tablename__ = "parties_players_hands"

  id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
  player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
  card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))

class PartyStock(Base):
  __tablename__ = "parties_stocks"
  
  id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
  card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))

class PartyTable(Base):
  __tablename__ = "parties_tables"
  
  id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
  card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))

def mapped_to_dict(model: Base) -> Dict:
  return {attr.name: getattr(model, attr.name) for attr in model.__table__.columns}

engin = create_engine("sqlite:///db.db")

Base.metadata.drop_all(engin)
Base.metadata.create_all(engin)


with Session(engin) as session:
  session.add(Player(name="Player0"))
  session.commit()
  print("Database created...")