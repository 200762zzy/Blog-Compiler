from typing import Optional
from publishers.csdn import CsdnPublisher
from publishers.juejin import JuejinPublisher
from publishers.cnblogs import CnblogsPublisher


_REGISTRY = {}


def init_publishers(settings):
    _REGISTRY.clear()
    publishers = [
        CsdnPublisher(settings),
        JuejinPublisher(settings),
        CnblogsPublisher(settings),
    ]
    for p in publishers:
        _REGISTRY[p.name] = p


def get_publishers():
    return list(_REGISTRY.values())


def get_publisher(name: str) -> Optional:
    return _REGISTRY.get(name)
