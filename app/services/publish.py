import os
import re

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import settings

INCLUDE_PATTERN = re.compile(r"<<[^.>]+\.\.[^>]*>>")
FIELD_PATTERN = re.compile(r"{{(\w+)}}")
FIRST_TAG_PATTERN = re.compile(r"<(.*?)>")


class RenderNode:
    """In-memory node + descendants, mirrors the original PHP Node/compile logic."""

    def __init__(self, doc: dict):
        self.id = doc["_id"]
        self.name = doc["name"]
        self.data = dict(doc.get("data") or {})
        self.children: list["RenderNode"] = []

    def template(self) -> str:
        return self.data.get("template", "") or ""

    def compile(self, values: dict) -> str:
        html = "".join(child.compile(values) for child in self.children)

        merged = dict(values)
        for key, value in self.data.items():
            if key in ("template", "name"):
                continue
            if isinstance(value, dict) and value.get("type") == "link":
                url, _, target = value.get("options", "").partition("|")
                text = value.get("value", "") or url
                target_attr = f' target="{target}"' if target else ""
                merged[key] = f'<a href="{url}"{target_attr}>{text}</a>'
            elif isinstance(value, dict):
                merged[key] = value.get("value", "")
            else:
                merged[key] = value
        merged["html"] = html
        merged["node_id"] = str(self.id)
        merged["name"] = self.name

        template = self.template()
        template = FIRST_TAG_PATTERN.sub(lambda m: f'<{m.group(1)} data-node-id="{self.id}">', template, count=1)

        template = INCLUDE_PATTERN.sub("", template)
        template = FIELD_PATTERN.sub(lambda m: str(merged.get(m.group(1), "")), template)
        return template


async def load_render_tree(db: AsyncIOMotorDatabase, doc: dict) -> RenderNode:
    render = RenderNode(doc)
    for child_id in doc.get("children", []):
        child = await db.nodes.find_one({"_id": child_id})
        if child is None:
            continue
        render.children.append(await load_render_tree(db, child))
    return render


async def get_path(db: AsyncIOMotorDatabase, doc: dict) -> str:
    """Filesystem directory a node's page should be written into, based on ancestor names."""
    parent_id = doc.get("parent")
    if parent_id is None:
        return settings.pages_dir

    parent = await db.nodes.find_one({"_id": parent_id})
    if parent is None or parent.get("parent") is None:
        return settings.pages_dir

    parent_dir = await get_path(db, parent)
    return os.path.join(parent_dir, parent["name"])


async def publish_node(db: AsyncIOMotorDatabase, doc: dict) -> str:
    """Render node + descendants and write to disk under pages/. Returns the output path."""
    if not doc["name"].endswith(".html"):
        raise ValueError("only .html nodes can be published")

    render = await load_render_tree(db, doc)
    out = render.compile({})

    directory = await get_path(db, doc)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, doc["name"])
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return path


async def preview_node(db: AsyncIOMotorDatabase, doc: dict) -> str:
    render = await load_render_tree(db, doc)
    return render.compile({})
