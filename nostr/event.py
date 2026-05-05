import hashlib
import json

from pydantic import BaseModel


class NostrEvent(BaseModel):
    id: str = ""
    pubkey: str
    created_at: int
    kind: int
    tags: list[list[str]] = []
    content: str = ""
    sig: str | None = None

    def serialize(self) -> list:
        return [0, self.pubkey, self.created_at, self.kind, self.tags, self.content]

    def serialize_json(self) -> str:
        e = self.serialize()
        return json.dumps(e, separators=(",", ":"), ensure_ascii=False)

    @property
    def event_id(self) -> str:
        data = self.serialize_json()
        return hashlib.sha256(data.encode()).hexdigest()
