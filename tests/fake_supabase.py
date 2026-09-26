"""
A small in-memory stand-in for the Supabase client, for tests only.

Supports the calls the app makes (table().select/insert/update/delete with
eq/gte/order/limit, and auth sign_up / sign_in / sign_out), and imitates Row
Level Security: a signed-in client only sees rows with its own user_id, and the
usage table is invisible to anyone but the admin (service key) client.
"""
import copy
import itertools
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

DB = {"chats": [], "messages": [], "usage": []}
USERS = {}          # email -> {"id", "password", "name"}
_clock = itertools.count()


def reset():
    for rows in DB.values():
        rows.clear()
    USERS.clear()


def _now_iso():
    # Strictly increasing timestamps so ordering is deterministic in tests.
    return (datetime.now(timezone.utc) + timedelta(microseconds=next(_clock))).isoformat()


class _Query:
    def __init__(self, client, table):
        self.client, self.table, self.filters, self.op = client, table, [], "select"
        self.payload, self._order, self._limit, self.cols = None, None, None, "*"

    # --- builders ---
    def select(self, cols="*", count=None):
        self.op, self.cols = "select", cols
        return self

    def insert(self, row):
        self.op, self.payload = "insert", row
        return self

    def update(self, values):
        self.op, self.payload = "update", values
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, col, val):
        self.filters.append(lambda r: r.get(col) == val)
        return self

    def gte(self, col, val):
        self.filters.append(lambda r: str(r.get(col)) >= str(val))
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
        return self

    def limit(self, n):
        self._limit = n
        return self

    # --- Row Level Security imitation ---
    def _visible(self, row):
        if self.client.is_admin:
            return True
        if self.table == "usage":
            return False                      # no policies: users can't see usage at all
        return self.client.user_id is not None and row.get("user_id") == self.client.user_id

    def execute(self):
        rows = DB[self.table]
        if self.op == "insert":
            row = dict(self.payload)
            if not self._visible(row) and not self.client.is_admin:
                raise PermissionError("new row violates row-level security policy")
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", _now_iso())
            if self.table == "chats":
                row.setdefault("updated_at", row["created_at"])
            rows.append(row)
            return SimpleNamespace(data=[copy.deepcopy(row)])

        matched = [r for r in rows if self._visible(r) and all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in matched:
                r.update(self.payload)
            return SimpleNamespace(data=copy.deepcopy(matched))
        if self.op == "delete":
            ids = {id(r) for r in matched}
            DB[self.table][:] = [r for r in rows if id(r) not in ids]
            if self.table == "chats":   # ON DELETE CASCADE
                chat_ids = {r["id"] for r in matched}
                DB["messages"][:] = [m for m in DB["messages"] if m["chat_id"] not in chat_ids]
            return SimpleNamespace(data=copy.deepcopy(matched))

        if self._order:
            col, desc = self._order
            matched = sorted(matched, key=lambda r: str(r.get(col)), reverse=desc)
        if self._limit:
            matched = matched[: self._limit]
        return SimpleNamespace(data=copy.deepcopy(matched))


class _Auth:
    def __init__(self, client):
        self.client = client

    def sign_up(self, creds):
        email = creds["email"]
        if email in USERS:
            raise Exception("User already registered")
        uid = str(uuid.uuid4())
        USERS[email] = {"id": uid, "password": creds["password"], "name": creds["options"]["data"]["name"]}
        return self._session(email)

    def sign_in_with_password(self, creds):
        u = USERS.get(creds["email"])
        if not u or u["password"] != creds["password"]:
            raise Exception("Invalid login credentials")
        return self._session(creds["email"])

    def sign_out(self):
        self.client.user_id = None

    def _session(self, email):
        u = USERS[email]
        self.client.user_id = u["id"]
        user = SimpleNamespace(id=u["id"], email=email, user_metadata={"name": u["name"]})
        return SimpleNamespace(user=user, session=SimpleNamespace(access_token="t"))


class FakeClient:
    def __init__(self, url, key):
        self.is_admin = key == "service-key"
        self.user_id = None
        self.auth = _Auth(self)

    def table(self, name):
        return _Query(self, name)


def create_client(url, key):
    return FakeClient(url, key)
