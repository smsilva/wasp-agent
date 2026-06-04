from wasp.auth.protocol import AuthRepository as AuthRepository

__all__ = ["AuthRepository", "get_repository"]

_repository = None


def get_repository():
    global _repository
    if _repository is None:
        from wasp.auth.repository import AuthRepository as _AuthRepository
        r = _AuthRepository()
        r.init_schema()
        _repository = r
    return _repository


def _reset_repository() -> None:
    global _repository
    _repository = None
