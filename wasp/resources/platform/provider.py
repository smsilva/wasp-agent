from collections.abc import Callable

from wasp.provision import list_platform_instances, provision_platform_instance


class PlatformProvider:
    name = "platform"

    def tools(self) -> list[Callable]:
        return [provision_platform_instance, list_platform_instances]
