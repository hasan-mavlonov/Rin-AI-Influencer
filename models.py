# models.py
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime

class PostDraft(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    idea: str = Field(default="")
    image_path: Optional[str] = None
    caption: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    posted: bool = Field(default=False)

class PostHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    draft_id: Optional[int] = Field(default=None, foreign_key="postdraft.id")
    instagram_post_id: Optional[str] = None
    posted_at: datetime = Field(default_factory=datetime.utcnow)
    likes: int = Field(default=0)
    comments: int = Field(default=0)
    followers_at_post: int = Field(default=0)
