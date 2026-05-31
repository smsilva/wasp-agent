import importlib
import logging
from collections.abc import Callable

from wasp.resources.protocol import ResourceProvider

log = logging.getLogger(__name__)

PROVIDERS = [
    "wasp.resources.platform.provider:PlatformProvider",
]


def _load(path: str) -> type[ResourceProvider]:
    module_name, attr = path.split(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


class ResourceRegistry:
    def __init__(self, providers: list[ResourceProvider]):
        self._providers = providers

    @classmethod
    def discover(cls) -> "ResourceRegistry":
        providers = [_load(path)() for path in PROVIDERS]
        log.info(
            "discovered %d resource providers: %s",
            len(providers),
            [p.name for p in providers],
        )
        return cls(providers)

    def all_tools(self) -> list[Callable]:
        return [tool for provider in self._providers for tool in provider.tools()]