import sys
from typing import Set

sys.path = sys.path[1:] + sys.path[:1]
import enum

sys.path = sys.path[-1:] + sys.path[:-1]


class EventType(enum.Enum):
    LINE = 0
    BRANCH = 1
    FUNCTION_ENTER = 2
    FUNCTION_EXIT = 3
    FUNCTION_ERROR = 4
    DEF = 5
    USE = 6
    CONDITION = 7
    LOOP_BEGIN = 8
    LOOP_HIT = 9
    LOOP_END = 10
    LEN = 11
    TEST_START = 12
    TEST_END = 13
    TEST_LINE = 14
    TEST_DEF = 15
    TEST_USE = 16
    TEST_ASSERT = 17

    @property
    def is_test(self):
        return self in self.test_events()

    @staticmethod
    def test_events() -> Set["EventType"]:
        return {EventType.TEST_LINE, EventType.TEST_DEF, EventType.TEST_USE}

    @staticmethod
    def events() -> Set["EventType"]:
        return set(EventType) - EventType.test_events()


__all__ = ["event", "EventType"]
