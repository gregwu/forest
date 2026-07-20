from app.config import settings


def url(path: str) -> str:
    """Prefix an absolute path with the app's mount base (e.g. '/forest' behind a reverse proxy).

    Idempotent: a path that's already prefixed is returned unchanged, so callers don't
    need to know whether `path` came from a URL-generating context (unprefixed,
    app-internal) or a browser-facing one (already prefixed).
    """
    if not path.startswith("/"):
        path = "/" + path
    if settings.base_path and (path == settings.base_path or path.startswith(settings.base_path + "/")):
        return path
    return settings.base_path + path
