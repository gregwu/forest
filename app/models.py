"""Thin typed helpers over raw Mongo documents.

Collections and their document shapes (mirrors the original app):

users:   { _id, username, password_hash, domain, is_admin }
nodes:   { _id, parent_id (ObjectId|None), name, position (int),
           data (dict), content (str), updated_by (str),
           updated_on (datetime), deleted (bool) }
history: { _id, node_id, name, data, updated_by, updated_on }
"""
from bson import ObjectId


def oid(value: str | ObjectId) -> ObjectId:
    return value if isinstance(value, ObjectId) else ObjectId(value)


def serialize_id(doc: dict) -> dict:
    """Convert ObjectId fields to strings for JSON/template rendering."""
    if doc is None:
        return doc
    out = dict(doc)
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    if out.get("parent_id") is not None:
        out["parent_id"] = str(out["parent_id"])
    if "node_id" in out and out["node_id"] is not None:
        out["node_id"] = str(out["node_id"])
    return out
