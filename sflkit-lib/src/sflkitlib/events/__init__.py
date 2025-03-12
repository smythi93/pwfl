import sys
from typing import Set, List

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

    @classmethod
    def events(cls) -> List["EventType"]:
        return [
            cls.LINE,
            cls.BRANCH,
            cls.FUNCTION_ENTER,
            cls.FUNCTION_EXIT,
            cls.FUNCTION_ERROR,
            cls.DEF,
            cls.USE,
            cls.CONDITION,
            cls.LOOP_BEGIN,
            cls.LOOP_HIT,
            cls.LOOP_END,
            cls.LEN,
        ]

    @classmethod
    def test_events(cls) -> List["EventType"]:
        return [
            cls.TEST_START,
            cls.TEST_END,
            cls.TEST_LINE,
            cls.TEST_DEF,
            cls.TEST_USE,
            cls.TEST_ASSERT,
        ]

    @property
    def is_test(self):
        return self in self.test_events()


__all__ = ["event", "EventType"]
