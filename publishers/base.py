from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PublishResult:
    success: bool
    platform: str
    url: str = ""
    error: str = ""


class BasePublisher(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    def display_name(self) -> str:
        return self.name

    @abstractmethod
    def is_logged_in(self) -> bool:
        ...

    def login(self, parent=None) -> bool:
        return True

    def logout(self):
        pass

    @abstractmethod
    def publish(self, title: str, content: str, **kwargs) -> PublishResult:
        ...

    def adapt_content(self, content: str) -> str:
        from exporter import Exporter
        return Exporter.adapt_for(self.name, content)
