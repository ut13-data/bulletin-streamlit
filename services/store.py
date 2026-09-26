"""
Where chats are kept. Both stores have the SAME methods, so app.py doesn't care which one it gets.

  SupabaseStore  the real one: chats and messages in Supabase, per logged-in user.
                 Row Level Security in the database makes sure a user only ever sees their own rows.
  SessionStore   in-memory, used by the tests (and handy for offline experiments).
"""
import json
import uuid
from datetime import datetime, timezone

import streamlit as st


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_title(question: str, limit: int = 40) -> str:
    """First 40 characters, cut back to the last full word."""
    q = " ".join(question.split())
    if len(q) <= limit:
        return q
    cut = q[:limit]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut) + "..."


class SessionStore:
    def __init__(self):
        st.session_state.setdefault("chats", {})

    @property
    def _chats(self) -> dict:
        return st.session_state["chats"]

    def list_chats(self) -> list[dict]:
        """Newest activity first."""
        return sorted(({"id": cid, **{k: c[k] for k in ("title", "updated_at")}} for cid, c in self._chats.items()),
                      key=lambda c: c["updated_at"], reverse=True)

    def create_chat(self) -> str:
        cid = str(uuid.uuid4())
        self._chats[cid] = {"title": "New chat", "created_at": _now(), "updated_at": _now(), "messages": []}
        return cid

    def chat_exists(self, chat_id: str) -> bool:
        return chat_id in self._chats

    def get_messages(self, chat_id: str) -> list[dict]:
        return self._chats.get(chat_id, {}).get("messages", [])

    def add_message(self, chat_id: str, role: str, content: str, response: dict | None = None):
        chat = self._chats[chat_id]
        chat["messages"].append({"role": role, "content": content, "response": response, "created_at": _now()})
        chat["updated_at"] = _now()
        if role == "user" and chat["title"] == "New chat":
            chat["title"] = make_title(content)

    def rename_chat(self, chat_id: str, title: str):
        if title.strip():
            self._chats[chat_id]["title"] = title.strip()[:80]

    def delete_chat(self, chat_id: str):
        self._chats.pop(chat_id, None)


def _ts(value) -> datetime:
    """Supabase returns ISO timestamps as text; turn them into timezone-aware datetimes."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _json_safe(obj):
    """Make sure the agent's response can be stored as JSON (numpy numbers, dates -> plain values)."""
    return json.loads(json.dumps(obj, default=str)) if obj is not None else None


class SupabaseStore:
    def __init__(self, client, user_id: str):
        self.db = client          # the logged-in user's client (Row Level Security applies)
        self.user_id = user_id

    def list_chats(self) -> list[dict]:
        # Row Level Security already limits rows to this user; the user_id filter is a second lock.
        rows = (self.db.table("chats").select("id, title, updated_at").eq("user_id", self.user_id)
                .order("updated_at", desc=True).limit(200).execute().data)
        return [{"id": r["id"], "title": r["title"], "updated_at": _ts(r["updated_at"])} for r in rows]

    def chat_exists(self, chat_id: str) -> bool:
        return bool(self.db.table("chats").select("id").eq("id", chat_id).eq("user_id", self.user_id).execute().data)

    def create_chat(self) -> str:
        row = self.db.table("chats").insert({"user_id": self.user_id, "title": "New chat"}).execute().data[0]
        return row["id"]

    def get_messages(self, chat_id: str) -> list[dict]:
        rows = (self.db.table("messages").select("role, content, response, created_at")
                .eq("chat_id", chat_id).eq("user_id", self.user_id).order("created_at").execute().data)
        return [{**r, "created_at": _ts(r["created_at"])} for r in rows]

    def add_message(self, chat_id: str, role: str, content: str, response: dict | None = None):
        self.db.table("messages").insert({"chat_id": chat_id, "user_id": self.user_id, "role": role,
                                          "content": content, "response": _json_safe(response)}).execute()
        self.db.table("chats").update({"updated_at": _now().isoformat()}).eq("id", chat_id).execute()
        if role == "user":
            # Only the first question names the chat (the title is still the default).
            (self.db.table("chats").update({"title": make_title(content)})
             .eq("id", chat_id).eq("title", "New chat").execute())

    def rename_chat(self, chat_id: str, title: str):
        if title.strip():
            self.db.table("chats").update({"title": title.strip()[:80]}).eq("id", chat_id).execute()

    def delete_chat(self, chat_id: str):
        # Messages are removed automatically (ON DELETE CASCADE in the schema).
        self.db.table("chats").delete().eq("id", chat_id).execute()


def history_for_agent(messages: list[dict]) -> list[dict]:
    """Pair each question with its answer, in the format run_agent() expects."""
    history, question = [], None
    for m in messages:
        if m["role"] == "user":
            question = m["content"]
        elif m["role"] == "assistant" and question is not None:
            r = m.get("response") or {}
            if r.get("route_decision") != "limit-reached":
                history.append({"question": question, "explanation": r.get("explanation", m["content"]),
                                "query": r.get("query")})
            question = None
    return history
