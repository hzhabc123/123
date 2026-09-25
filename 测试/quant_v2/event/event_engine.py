"""
Quant V2 事件引擎

基于事件的异步调度核心：
- 事件订阅/发布
- 多策略、多模块解耦
"""

import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from core.enums import EventType


@dataclass
class Event:
    event_type: EventType
    data: object
    timestamp: datetime = field(default_factory=datetime.now)
    sender: str = ""

    def __repr__(self) -> str:
        return f"Event({self.event_type.name}, {self.timestamp}, sender={self.sender})"


class EventHandler:
    def __init__(self, handler: Callable[[Event], None], priority: int = 0):
        self.handler = handler
        self.priority = priority

    def __call__(self, event: Event):
        self.handler(event)


class EventEngine:

    def __init__(self):
        self._subscribers: Dict[EventType, List[EventHandler]] = defaultdict(list)
        self._lock = threading.RLock()
        self._handled_count: int = 0

    def subscribe(self, event_type: EventType, handler: Callable, priority: int = 0):
        with self._lock:
            self._subscribers[event_type].append(EventHandler(handler, priority))
            self._subscribers[event_type].sort(key=lambda h: -h.priority)

    def unsubscribe(self, event_type: EventType, handler: Callable):
        with self._lock:
            before = len(self._subscribers[event_type])
            self._subscribers[event_type] = [h for h in self._subscribers[event_type] if h.handler is not handler]
            return len(self._subscribers[event_type]) < before

    def put(self, event: Event):
        with self._lock:
            handlers = list(self._subscribers.get(event.event_type, []))
        for eh in handlers:
            try:
                eh(event)
                with self._lock:
                    self._handled_count += 1
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception("事件处理失败: %s", e)

    def emit(self, event_type: EventType, data: object, sender: str = ""):
        self.put(Event(event_type, data, sender=sender))

    @property
    def handled_count(self) -> int:
        with self._lock:
            return self._handled_count

    def clear_all(self):
        with self._lock:
            self._subscribers.clear()

    def subscriptions(self) -> Dict[EventType, int]:
        with self._lock:
            return {t: len(h) for t, h in self._subscribers.items()}


_default_engine: Optional[EventEngine] = None


def get_default_engine() -> EventEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = EventEngine()
    return _default_engine
