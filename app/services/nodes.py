import datetime
import re

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import oid

ROOT_NAME = "All"


class NodeError(Exception):
    pass


async def get_root(db: AsyncIOMotorDatabase) -> dict | None:
    return await db.nodes.find_one({"parent": None, "deleted": {"$ne": True}})


async def ensure_root(db: AsyncIOMotorDatabase, admin_username: str) -> dict:
    root = await get_root(db)
    if root:
        return root
    doc = {
        "name": ROOT_NAME,
        "parent": None,
        "children": [],
        "data": {},
        "content": "",
        "updated_by": admin_username,
        "updated_on": datetime.datetime.now(datetime.timezone.utc),
        "deleted": False,
    }
    result = await db.nodes.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_node(db: AsyncIOMotorDatabase, node_id: str | ObjectId) -> dict | None:
    return await db.nodes.find_one({"_id": oid(node_id), "deleted": {"$ne": True}})


def can_access(node: dict, username: str) -> bool:
    return node.get("updated_by") == username or node.get("updated_by") == "admin" or node.get("parent") is None


async def build_tree(db: AsyncIOMotorDatabase, username: str) -> dict:
    """Load all nodes visible to `username` (their own + admin's), build nested dict tree from root."""
    cursor = db.nodes.find(
        {"deleted": {"$ne": True}, "updated_by": {"$in": [username, "admin"]}},
        {"name": 1, "children": 1, "parent": 1},
    )
    by_id: dict[str, dict] = {}
    async for doc in cursor:
        by_id[str(doc["_id"])] = doc

    root = next((d for d in by_id.values() if d.get("parent") is None), None)
    if root is None:
        return {}

    def serialize(node: dict, seen: set[str]) -> dict:
        node_id = str(node["_id"])
        seen.add(node_id)
        kids = []
        for child_id in node.get("children", []):
            child = by_id.get(str(child_id))
            if child is not None and str(child["_id"]) not in seen:
                kids.append(serialize(child, seen))
        return {"id": node_id, "name": node["name"], "children": kids}

    return serialize(root, set())


async def add_node(db: AsyncIOMotorDatabase, parent: dict, name: str, username: str) -> dict:
    doc = {
        "name": name,
        "parent": parent["_id"],
        "children": [],
        "data": {},
        "content": "",
        "updated_by": username,
        "updated_on": datetime.datetime.now(datetime.timezone.utc),
        "deleted": False,
    }
    result = await db.nodes.insert_one(doc)
    doc["_id"] = result.inserted_id
    await db.nodes.update_one({"_id": parent["_id"]}, {"$push": {"children": doc["_id"]}})
    return doc


async def rename_node(db: AsyncIOMotorDatabase, node: dict, new_name: str) -> dict:
    await db.nodes.update_one({"_id": node["_id"]}, {"$set": {"name": new_name}})
    node["name"] = new_name
    return node


async def remove_node(db: AsyncIOMotorDatabase, node: dict) -> None:
    if node.get("children"):
        raise NodeError("has children")
    if node.get("parent") is not None:
        await db.nodes.update_one({"_id": node["parent"]}, {"$pull": {"children": node["_id"]}})
    await db.nodes.delete_one({"_id": node["_id"]})


async def move_node(db: AsyncIOMotorDatabase, node: dict, target: dict, position: str) -> None:
    """position: 'inside' -> make node first child of target; 'after' -> sibling after target."""
    if position == "inside":
        new_parent_id = target["_id"]
    elif position == "after":
        if target.get("parent") is None:
            raise NodeError("cannot move after root")
        new_parent_id = target["parent"]
    else:
        raise NodeError(f"invalid position: {position}")

    if node.get("parent") is not None:
        await db.nodes.update_one({"_id": node["parent"]}, {"$pull": {"children": node["_id"]}})

    await db.nodes.update_one({"_id": node["_id"]}, {"$set": {"parent": new_parent_id}})

    if position == "inside":
        await db.nodes.update_one({"_id": new_parent_id}, {"$push": {"children": {"$each": [node["_id"]], "$position": 0}}})
    else:
        new_parent = await db.nodes.find_one({"_id": new_parent_id})
        children = list(new_parent.get("children", []))
        idx = next((i for i, c in enumerate(children) if c == target["_id"]), None)
        if idx is None:
            raise NodeError("cannot find target position")
        insert_at = idx + 1
        await db.nodes.update_one(
            {"_id": new_parent_id},
            {"$push": {"children": {"$each": [node["_id"]], "$position": insert_at}}},
        )


async def _clone_subtree(db: AsyncIOMotorDatabase, node: dict, new_parent_id: ObjectId | None, username: str) -> dict:
    clone_doc = {
        "name": node["name"],
        "parent": new_parent_id,
        "children": [],
        "data": node.get("data", {}),
        "content": node.get("content", ""),
        "updated_by": username,
        "updated_on": datetime.datetime.now(datetime.timezone.utc),
        "deleted": False,
    }
    result = await db.nodes.insert_one(clone_doc)
    clone_doc["_id"] = result.inserted_id

    child_ids = []
    for child_id in node.get("children", []):
        child = await db.nodes.find_one({"_id": child_id})
        if child is None:
            continue
        child_clone = await _clone_subtree(db, child, clone_doc["_id"], username)
        child_ids.append(child_clone["_id"])

    if child_ids:
        await db.nodes.update_one({"_id": clone_doc["_id"]}, {"$set": {"children": child_ids}})
        clone_doc["children"] = child_ids

    return clone_doc


async def copy_node(db: AsyncIOMotorDatabase, node: dict, username: str) -> dict:
    """Duplicate node (and descendants) as a sibling placed right after it."""
    parent_id = node.get("parent")
    if parent_id is None:
        raise NodeError("cannot duplicate root")

    clone = await _clone_subtree(db, node, parent_id, username)

    parent = await db.nodes.find_one({"_id": parent_id})
    children = list(parent.get("children", []))
    idx = next((i for i, c in enumerate(children) if c == node["_id"]), None)
    if idx is None:
        raise NodeError("cannot find target position")
    insert_at = idx + 1
    await db.nodes.update_one(
        {"_id": parent_id},
        {"$push": {"children": {"$each": [clone["_id"]], "$position": insert_at}}},
    )
    return clone


def _extract_content(data: dict) -> str:
    parts = []
    for key, value in data.items():
        if key == "node_id":
            continue
        if key in ("template", "name"):
            text = value if isinstance(value, str) else ""
        elif isinstance(value, dict):
            text = str(value.get("value", ""))
        else:
            text = str(value)
        text = re.sub(r"{{.*?}}", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\s+", " ", text)
        parts.append(text.strip())
    return " ".join(p for p in parts if p)


async def save_node_data(db: AsyncIOMotorDatabase, node: dict, data: dict, username: str) -> dict:
    content = _extract_content(data)
    name = data.get("name")
    now = datetime.datetime.now(datetime.timezone.utc)

    await db.history.insert_one(
        {"node_id": node["_id"], "name": name, "data": data, "updated_by": username, "updated_on": now}
    )

    update = {"data": data, "content": content, "updated_by": username, "updated_on": now}
    if name:
        update["name"] = name

    await db.nodes.update_one({"_id": node["_id"]}, {"$set": update})
    node.update(update)
    return node


async def _export_subtree(db: AsyncIOMotorDatabase, node: dict) -> dict:
    children = []
    for child_id in node.get("children", []):
        child = await db.nodes.find_one({"_id": child_id, "deleted": {"$ne": True}})
        if child is None:
            continue
        children.append(await _export_subtree(db, child))
    return {"name": node["name"], "data": node.get("data") or {}, "children": children}


async def export_user_tree(db: AsyncIOMotorDatabase, username: str) -> dict:
    """Export every top-level node owned by `username` (i.e. direct children of root) as portable JSON."""
    root = await get_root(db)
    if root is None:
        return {"username": username, "nodes": []}

    nodes = []
    for child_id in root.get("children", []):
        child = await db.nodes.find_one({"_id": child_id, "deleted": {"$ne": True}})
        if child is None or child.get("updated_by") != username:
            continue
        nodes.append(await _export_subtree(db, child))

    return {"username": username, "nodes": nodes}


async def _import_subtree(db: AsyncIOMotorDatabase, item: dict, parent_id: ObjectId, username: str) -> dict:
    doc = {
        "name": item.get("name", "untitled"),
        "parent": parent_id,
        "children": [],
        "data": item.get("data") or {},
        "content": _extract_content(item.get("data") or {}),
        "updated_by": username,
        "updated_on": datetime.datetime.now(datetime.timezone.utc),
        "deleted": False,
    }
    result = await db.nodes.insert_one(doc)
    doc["_id"] = result.inserted_id

    child_ids = []
    for child_item in item.get("children", []):
        child_doc = await _import_subtree(db, child_item, doc["_id"], username)
        child_ids.append(child_doc["_id"])

    if child_ids:
        await db.nodes.update_one({"_id": doc["_id"]}, {"$set": {"children": child_ids}})
        doc["children"] = child_ids

    return doc


async def import_user_tree(db: AsyncIOMotorDatabase, export: dict, username: str) -> int:
    """Import an export_user_tree() payload as new top-level nodes owned by `username`. Returns count imported."""
    root = await ensure_root(db, "admin")
    nodes = export.get("nodes", [])

    imported_ids = []
    for item in nodes:
        doc = await _import_subtree(db, item, root["_id"], username)
        imported_ids.append(doc["_id"])

    if imported_ids:
        await db.nodes.update_one({"_id": root["_id"]}, {"$push": {"children": {"$each": imported_ids}}})

    return len(imported_ids)


async def search_nodes(db: AsyncIOMotorDatabase, term: str, username: str) -> list[dict]:
    cursor = db.nodes.find(
        {
            "deleted": {"$ne": True},
            "updated_by": username,
            "$or": [
                {"name": {"$regex": re.escape(term), "$options": "i"}},
                {"content": {"$regex": re.escape(term), "$options": "i"}},
            ],
        },
        {"name": 1, "content": 1},
    )
    return [doc async for doc in cursor]
