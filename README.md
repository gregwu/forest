# Forest

A tree-based web page/content builder. Users build a hierarchy of nodes, each with
an HTML template and typed fields (text, textarea, rich text, images, etc.), and
publish the tree to static HTML files.

FastAPI + HTMX rewrite of the original PHP/jQuery `tree` app, backed by MongoDB.

## Stack

- **Backend**: FastAPI, Motor (async MongoDB driver), Jinja2 templates
- **Frontend**: HTMX for all interactivity, vanilla JS for the tree/field-editor
  widgets, CKEditor 4 for rich-text fields
- **Auth**: signed session cookies (`starlette` `SessionMiddleware`) + bcrypt password hashing
- **Data**: MongoDB (`nodes`, `users`, `history` collections)

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and adjust as needed (defaults to a local Mongo on
`localhost:27017`).

Start MongoDB:

```bash
docker compose up -d
```

Create an admin user:

```bash
python scripts/seed_admin.py admin <password> admin
```

Run the app:

```bash
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/login`.

## Concepts

- **Node**: an item in the tree. Has a `name`, a `template` (HTML with `{{field}}`
  placeholders and `{{html}}` for child content), and arbitrary typed `data` fields.
- **Root**: the node with no parent, auto-created on first use, named `All`.
- **Ownership**: a node belongs to the user who created it (`updated_by`). Users only
  see their own nodes plus the `admin` user's nodes.
- **Publish**: walks a node (must end in `.html`) and its descendants, renders the
  template tree to a single HTML string, and writes it to `pages/` mirroring the
  tree's directory structure (based on ancestor node names).
- **Preview**: same render, returned inline without writing to disk.

## Project layout

```
app/
  main.py            FastAPI app + middleware + router registration
  config.py          Settings (reads .env)
  database.py        Motor client + index setup
  auth.py            Session helpers, password hashing, auth dependencies
  models.py          Thin helpers over raw Mongo documents
  services/
    nodes.py         Tree CRUD (add/rename/move/copy/delete/save/search)
    publish.py       Template compile + publish-to-disk engine
  routers/
    auth.py          /login /logout /register /user /forgot
    users.py         /users admin page + role/delete/login-as
    nodes.py         /api/tree /api/nodes/* /api/search
    publish.py       /api/nodes/{id}/publish /preview
  templates/         Jinja2 templates (HTMX partials under templates/partials/)
  static/css/        Stylesheet
scripts/
  seed_admin.py      Create the first admin user
pages/               Published static HTML output
```
# forest
