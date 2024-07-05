from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.sql import func
from sqlalchemy.types import TypeDecorator, TEXT
import json

from config import DATABASE_URL

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



class JSONType(TypeDecorator):
    impl = TEXT

    def process_bind_param(self, value, dialect):
        if value is None:
            return '{}'
        return json.dumps(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return {}
        return json.loads(value)

class Command(Base):
    __tablename__ = "commands"
    id = Column(Integer, primary_key=True, index=True)
    command = Column(String, unique=True, index=True)
    description = Column(String)
    response = Column(String)
    is_command = Column(Boolean, default=False)
    image_url = Column(String, nullable=True)
    inline_links = Column(JSON, nullable=True)
    markup_buttons = Column(JSON, nullable=True)  # New field for markup buttons


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String, unique=True, index=True, nullable=True)
    first_name = Column(String)
    last_name = Column(String, nullable=True)
    referral_id = Column(String, unique=True, index=True)
    referer_id = Column(Integer, ForeignKey('users.id'))
    referer = relationship('User', back_populates='downlines')
    created_at = Column(String, default=func.now())
    earnings = Column(Float, default=0.0)
    downline_earnings = Column(Float, default=0.0)
    downlines = relationship('User', back_populates='referer', remote_side=[id])
    total_earnings = Column(Float, default=0.0)
    referrals = Column(JSON, default=[])

class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)

class Settings(Base):
    __tablename__ = "settings"
    id = Column(Integer, primary_key=True, index=True)
    referral_earning = Column(Float, default=0.0)
    downline_earning = Column(Float, default=0.0)
    chats_to_join = Column(JSONType, default=[])
    strict_join = Column(Boolean, default=False)  # Strict join boolean
    broadcast_chat = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)
