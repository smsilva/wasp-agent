import logging
from collections.abc import Callable
from importlib.metadata import entry_points

from wasp.resources.protocol import ResourceProvider

log = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "wasp_agent.resources"


class ResourceRegistry:
    def __init__(self, providers: list[ResourceProvider]):
        self._providers = providers

    @classmethod
    def discover(cls) -> "ResourceRegistry":
        providers = [ep.load()() for ep in entry_points(group=ENTRY_POINT_GROUP)]
        log.info(
            "discovered %d resource providers: %s",
            len(providers),
            [p.name for p in providers],
        )
        return cls(providers)

    def all_tools(self) -> list[Callable]:
        return [tool for provider in self._providers for tool in provider.tools()]
