import pathlib
import sqlite3
from functools import cached_property

from remember_me_mcp_server.errors import ResourceError


ALLOWED_RULE_POLICIES = {"MUST", "MUST NOT", "SHOULD", "SHOULD NOT", "MAY"}


class PersistentResource:
    @classmethod
    def db_table(cls, cursor):
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {cls.resource_table} (
            type TEXT,
            context TEXT,
            key TEXT,
            {cls.resource_name} TEXT,
            UNIQUE(key, context)
        )
        """)

    def __init__(self, db) -> None:
        self.db = db

    def get(self, context: str, key: str) -> str:
        cursor = self.db.cursor()
        cursor.execute(
            f"SELECT {self.resource_name}, type FROM {self.resource_table} WHERE context = ? AND key = ?",
            (context, key))
        result = cursor.fetchone()
        if not result:
            raise ResourceError(f"{self.resource_name.capitalize()} ({context}/{key}) not found")
        return result

    def list(
            self,
            context: str,
            include_content=False
    ) -> list[dict]:
        cursor = self.db.cursor()
        cursor.execute(*
            (f"SELECT key, type, {self.resource_name} FROM {self.resource_table} WHERE context = ?",
             (context,))
            if include_content
            else (f"SELECT key, type FROM {self.resource_table} WHERE context = ?",
                  (context,)))
        return [
            {"key": row[0], "mime_type": row[1], self.resource_name: row[2]}
            if include_content
            else {"key": row[0], "mime_type": row[1]}
            for row in cursor.fetchall()]

    def remove(self, context: str, key: str) -> str:
        cursor = self.db.cursor()
        cursor.execute(
            f"DELETE FROM {self.resource_table} WHERE context = ? AND key = ?",
            (context, key))
        affected = cursor.rowcount
        self.db.commit()
        if affected > 0:
            return f"{self.resource_name.capitalize()} '{context}/{key}' removed successfully"
        raise ResourceError(f"{self.resource_name.capitalize()} '{context}/{key}' not found")

    def set(
            self,
            context: str,
            key: str,
            resource: str,
            mime_type: str) -> str:
        cursor = self.db.cursor()
        cursor.execute(
            f"UPDATE {self.resource_table} SET type = ?, {self.resource_name} = ? WHERE key = ? AND context IS ?",
            (mime_type, resource, key, context))
        status_message = f"Existing {self.resource_name} ({context}/{key} {mime_type}) updated"
        if cursor.rowcount == 0:
            status_message = f"New {self.resource_name} ({context}/{key} {mime_type}) added"
            cursor.execute(
                f"INSERT INTO {self.resource_table} (type, key, {self.resource_name}, context) VALUES (?, ?, ?, ?)",
                (mime_type, key, resource, context))
            if cursor.rowcount == 0:
                raise ResourceError(f"Failed to set {self.resource_name} ({context}/{key} {mime_type})")
        self.db.commit()
        return status_message


class Rule(PersistentResource):
    resource_name = "rule"
    resource_table = "rules"

    @classmethod
    def db_table(cls, cursor):
        cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {cls.resource_table} (
            context TEXT,
            policy TEXT CHECK(policy IN ('MUST', 'MUST NOT', 'SHOULD', 'SHOULD NOT', 'MAY')),
            rule TEXT,
            UNIQUE(context, {cls.resource_name})
        )""")

    def get(self, context: str, key: str) -> str:
        raise NotImplementedError

    def list(
            self,
            context: str,
            include_content=False) -> list[dict]:
        cursor = self.db.cursor()
        cursor.execute(
            f"SELECT policy, {self.resource_name} FROM {self.resource_table} WHERE context = ?",
            (context,))
        return [
            {"policy": row[0], self.resource_name: row[1]}
            for row in cursor.fetchall()]

    def remove(self, context: str, rule: str) -> str:
        cursor = self.db.cursor()
        if context is None:
            cursor.execute("SELECT policy FROM rules WHERE rule = ? AND context IS NULL", (rule,))
        else:
            cursor.execute("SELECT policy FROM rules WHERE rule = ? AND context = ?", (rule, context))
        result = cursor.fetchone()
        if not result:
            raise ResourceError(f"Rule '{rule}' not found with the specified context")
        if context is None:
            cursor.execute("DELETE FROM rules WHERE rule = ? AND context IS NULL", (rule,))
        else:
            cursor.execute("DELETE FROM rules WHERE rule = ? AND context = ?", (rule, context))
        if not cursor.rowcount:
            raise ResourceError(f"Rule '{rule}' not removed")
        self.db.commit()
        return f"Rule '{rule}' removed successfully"

    def set(self, context: str, policy: str, rule: str) -> str:
        if policy not in ALLOWED_RULE_POLICIES:
            raise ResourceError(f"Invalid policy '{policy}'. Must be one of: {sorted(ALLOWED_RULE_POLICIES)}")
        cursor = self.db.cursor()
        cursor.execute("SELECT policy FROM rules WHERE rule = ? AND context IS ?", (rule, context))
        row = cursor.fetchone()
        if row:
            existing_policy = row[0]
            if existing_policy == policy:
                raise ResourceError("Rule already exists with the same policy and context")
            cursor.execute("UPDATE rules SET policy = ? WHERE rule = ? AND context IS ?", (policy, rule, context))
            self.db.commit()
            return f"Policy updated from '{existing_policy}' to '{policy}'"
        cursor.execute("INSERT INTO rules (policy, rule, context) VALUES (?, ?, ?)", (policy, rule, context))
        self.db.commit()
        return "New rule added"


class Snippet(PersistentResource):
    resource_name = "snippet"
    resource_table = "snippet"


class Summary(PersistentResource):
    resource_name = "summary"
    resource_table = "summary"


class MyContext:
    resource_types = (
        ("rule", Rule),
        ("snippet", Snippet),
        ("summary", Summary))

    def __init__(self, db) -> None:
        self._db = db

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def __getitem__(self, key: str) -> PersistentResource:
        return self.resources[key]

    @cached_property
    def db(self):
        return self.create_db()

    @property
    def db_path(self) -> pathlib.Path:
        return pathlib.Path(self._db)

    @cached_property
    def resources(self) -> dict[str, PersistentResource]:
        return {
            name: resource(self.db)
            for name, resource
            in self.resource_types}

    def close(self):
        self.db.close()

    def create_db(self):
        self.db_path.parent.mkdir(exist_ok=True, parents=True)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        for _, resource in self.resource_types:
            resource.db_table(cursor)
        return conn
