import io
import sys
from abc import abstractmethod, ABC
from typing import Any, List, Union, BinaryIO, Dict

from sflkitlib.events import EventType
from sflkitlib.events.codec import (
    encode_event,
    encode_def_event,
    encode_function_exit_event,
    encode_condition_event,
    encode_use_event,
    encode_len_event,
    ENDIAN,
    encode_base_def_event,
)

sys.path = sys.path[1:] + sys.path[:1]
import json
import pickle

sys.path = sys.path[-1:] + sys.path[:-1]


class Event(ABC):
    def __init__(self, file: str, line: int, event_id: int, event_type: EventType):
        self.file = file
        self.line = line
        self.event_id = event_id
        self.event_type = event_type

    def __hash__(self):
        return hash((self.file, self.line, self.event_id, self.event_type.value))

    def __eq__(self, other):
        if isinstance(other, Event):
            return (
                self.file == other.file
                and self.line == other.line
                and self.event_id == other.event_id
                and self.event_type == other.event_type
            )
        return False

    def __repr__(self):
        return f"{self.__class__.__name__}({self.file},{self.line},{self.event_id})"

    @abstractmethod
    def handle(self, model: Any):
        raise NotImplementedError()

    def serialize(self):
        return {
            "file": self.file,
            "line": self.line,
            "id": self.event_id,
            "event_type": self.event_type.value,
        }

    @staticmethod
    def get_byte_length(x: Union[int, float]):
        return (x.bit_length() + 7) // 8

    def dump(self) -> bytes:
        return encode_event(self.event_id)

    @staticmethod
    def deserialize(s: dict):
        return None

    @abstractmethod
    def instantiate(self, *args, **kwargs):
        raise NotImplementedError


class EventEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, Event):
            return o.serialize()
        else:
            super().default(o)


class LineEvent(Event):
    def __init__(self, file: str, line: int, event_id: int):
        super().__init__(file, line, event_id, EventType.LINE)

    def handle(self, model: Any):
        model.handle_line_event(self)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id"])
        assert s["event_type"] == EventType.LINE.value
        return LineEvent(*[s[p] for p in ["file", "line", "id"]])

    def instantiate(self):
        return LineEvent(self.file, self.line, self.event_id)


class BranchEvent(Event):
    def __init__(self, file: str, line: int, event_id: int, then_id: int, else_id: int):
        super().__init__(file, line, event_id, EventType.BRANCH)
        self.then_id = then_id
        self.else_id = else_id

    def handle(self, model: Any):
        model.handle_branch_event(self)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},{self.then_id},{self.else_id})"

    def serialize(self):
        default = super().serialize()
        default["then_id"] = self.then_id
        default["else_id"] = self.else_id
        return default

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "then_id", "else_id"])
        assert s["event_type"] == EventType.BRANCH.value
        return BranchEvent(
            *[s[p] for p in ["file", "line", "id", "then_id", "else_id"]]
        )

    def instantiate(self):
        return BranchEvent(
            self.file, self.line, self.event_id, self.then_id, self.else_id
        )


class DefEvent(Event):
    def __init__(
        self,
        file,
        line: int,
        event_id: int,
        var: str,
        var_id: int = None,
        value: Any = None,
        type_: str = None,
    ):
        super().__init__(file, line, event_id, EventType.DEF)
        self.var = var
        self.var_id = var_id
        self.value = value
        self.type_ = type_

    def __repr__(self):
        return (
            f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},"
            f"{self.var},{self.var_id},{self.value})"
        )

    def handle(self, model: Any):
        model.handle_def_event(self)

    def serialize(self):
        default = super().serialize()
        default["var"] = self.var
        return default

    def dump(self):
        return encode_def_event(
            self.event_id,
            self.var_id,
            self.value,
            self.type_,
        )

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "var"])
        assert s["event_type"] == EventType.DEF.value
        return DefEvent(*[s[p] for p in ["file", "line", "id", "var"]])

    def instantiate(
        self,
        var_id: int,
        value: Any,
        type_: str,
    ):
        return DefEvent(
            self.file, self.line, self.event_id, self.var, var_id, value, type_
        )


class FunctionEvent(Event, ABC):
    def __init__(
        self,
        file: str,
        line: int,
        event_id: int,
        event_type: EventType,
        function: str,
        function_id: int,
    ):
        super().__init__(file, line, event_id, event_type)
        self.function = function
        self.function_id = function_id

    def serialize(self):
        default = super().serialize()
        default["function"] = self.function
        default["function_id"] = self.function_id
        return default


class FunctionEnterEvent(FunctionEvent):
    def __init__(
        self, file: str, line: int, event_id: int, function: str, function_id: int
    ):
        super().__init__(
            file, line, event_id, EventType.FUNCTION_ENTER, function, function_id
        )

    def __repr__(self):
        return f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},{self.function})"

    def handle(self, model: Any):
        model.handle_function_enter_event(self)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "function", "function_id"])
        assert s["event_type"] == EventType.FUNCTION_ENTER.value
        return FunctionEnterEvent(
            *[s[p] for p in ["file", "line", "id", "function", "function_id"]]
        )

    def instantiate(self):
        return FunctionEnterEvent(
            self.file, self.line, self.event_id, self.function, self.function_id
        )


class FunctionExitEvent(FunctionEvent):
    def __init__(
        self,
        file: str,
        line: int,
        event_id: int,
        function: str,
        function_id: int,
        tmp_var: str,
        return_value: Any = None,
        type_: str = None,
    ):
        super().__init__(
            file, line, event_id, EventType.FUNCTION_EXIT, function, function_id
        )
        self.tmp_var = tmp_var
        self.return_value = return_value
        self.type_ = type_

    def __repr__(self):
        return (
            f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},"
            f"{self.function},{self.return_value},{self.type_})"
        )

    def handle(self, model: Any):
        model.handle_function_exit_event(self)

    def dump(self):
        return encode_function_exit_event(self.event_id, self.return_value, self.type_)

    def serialize(self):
        default = super().serialize()
        default["tmp_var"] = self.tmp_var
        return default

    @staticmethod
    def deserialize(s: dict):
        assert all(
            p in s for p in ["file", "line", "id", "function", "function_id", "tmp_var"]
        )
        assert s["event_type"] == EventType.FUNCTION_EXIT.value
        return FunctionExitEvent(
            *[
                s[p]
                for p in ["file", "line", "id", "function", "function_id", "tmp_var"]
            ]
        )

    def instantiate(
        self,
        return_value: Any,
        type_: str,
    ):
        return FunctionExitEvent(
            self.file,
            self.line,
            self.event_id,
            self.function,
            self.function_id,
            self.tmp_var,
            return_value,
            type_,
        )


class FunctionErrorEvent(FunctionEvent):
    def __init__(
        self, file: str, line: int, event_id: int, function: str, function_id: int
    ):
        super().__init__(
            file, line, event_id, EventType.FUNCTION_ERROR, function, function_id
        )

    def __repr__(self):
        return f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},{self.function},{self.function_id})"

    def handle(self, model: Any):
        model.handle_function_error_event(self)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "function", "function_id"])
        assert s["event_type"] == EventType.FUNCTION_ERROR.value
        return FunctionErrorEvent(
            *[s[p] for p in ["file", "line", "id", "function", "function_id"]]
        )

    def instantiate(self):
        return FunctionErrorEvent(
            self.file, self.line, self.event_id, self.function, self.function_id
        )


class ConditionEvent(Event):
    def __init__(
        self,
        file: str,
        line: int,
        event_id: int,
        condition: str,
        tmp_var: str,
        value: bool = None,
    ):
        super().__init__(file, line, event_id, EventType.CONDITION)
        self.value = value
        self.tmp_var = tmp_var
        self.condition = condition

    def __repr__(self):
        return f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},{self.value},{self.condition})"

    def handle(self, model: Any):
        model.handle_condition_event(self)

    def serialize(self):
        default = super().serialize()
        default["condition"] = self.condition
        default["tmp_var"] = self.tmp_var
        return default

    def dump(self):
        return encode_condition_event(
            self.event_id,
            self.value,
        )

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "condition", "tmp_var"])
        assert s["event_type"] == EventType.CONDITION.value
        return ConditionEvent(
            *[s[p] for p in ["file", "line", "id", "condition", "tmp_var"]]
        )

    def instantiate(
        self,
        value: bool,
    ):
        return ConditionEvent(
            self.file,
            self.line,
            self.event_id,
            self.condition,
            self.tmp_var,
            value,
        )


class LoopEvent(Event, ABC):
    def __init__(
        self, file: str, line: int, event_id: int, event_type: EventType, loop_id: int
    ):
        super().__init__(file, line, event_id, event_type)
        self.loop_id = loop_id

    def serialize(self):
        default = super().serialize()
        default["loop_id"] = self.loop_id
        return default


class LoopBeginEvent(LoopEvent):
    def __init__(self, file: str, line: int, event_id: int, loop_id: int):
        super().__init__(file, line, event_id, EventType.LOOP_BEGIN, loop_id)

    def handle(self, model: Any):
        model.handle_loop_begin_event(self)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "loop_id"])
        assert s["event_type"] == EventType.LOOP_BEGIN.value
        return LoopBeginEvent(*[s[p] for p in ["file", "line", "id", "loop_id"]])

    def instantiate(self):
        return LoopBeginEvent(self.file, self.line, self.event_id, self.loop_id)


class LoopHitEvent(LoopEvent):
    def __init__(self, file: str, line: int, event_id: int, loop_id: int):
        super().__init__(file, line, event_id, EventType.LOOP_HIT, loop_id)

    def handle(self, model: Any):
        model.handle_loop_hit_event(self)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "loop_id"])
        assert s["event_type"] == EventType.LOOP_HIT.value
        return LoopHitEvent(*[s[p] for p in ["file", "line", "id", "loop_id"]])

    def instantiate(self):
        return LoopHitEvent(self.file, self.line, self.event_id, self.loop_id)


class LoopEndEvent(LoopEvent):
    def __init__(self, file: str, line: int, event_id: int, loop_id: int):
        super().__init__(file, line, event_id, EventType.LOOP_END, loop_id)

    def handle(self, model: Any):
        model.handle_loop_end_event(self)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "loop_id"])
        assert s["event_type"] == EventType.LOOP_END.value
        return LoopEndEvent(*[s[p] for p in ["file", "line", "id", "loop_id"]])

    def instantiate(self):
        return LoopEndEvent(self.file, self.line, self.event_id, self.loop_id)


class UseEvent(Event):
    def __init__(
        self, file: str, line: int, event_id: int, var: str, var_id: int = None
    ):
        super().__init__(file, line, event_id, EventType.USE)
        self.var = var
        self.var_id = var_id

    def __repr__(self):
        return f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},{self.var},{self.var_id})"

    def handle(self, model: Any):
        model.handle_use_event(self)

    def serialize(self):
        default = super().serialize()
        default["var"] = self.var
        return default

    def dump(self):
        return encode_use_event(self.event_id, self.var_id)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "var"])
        assert s["event_type"] == EventType.USE.value
        return UseEvent(*[s[p] for p in ["file", "line", "id", "var"]])

    def instantiate(self, var_id):
        return UseEvent(self.file, self.line, self.event_id, self.var, var_id)


class LenEvent(Event):
    def __init__(
        self,
        file: str,
        line: int,
        event_id: int,
        var: str,
        var_id: int = None,
        length: int = None,
    ):
        super().__init__(file, line, event_id, EventType.LEN)
        self.var = var
        self.var_id = var_id
        self.length = length

    def __repr__(self):
        return (
            f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},"
            f"{self.var},{self.var_id},{self.length})"
        )

    def handle(self, model: Any):
        model.handle_len_event(self)

    def serialize(self):
        default = super().serialize()
        default["var"] = self.var
        return default

    def dump(self):
        return encode_len_event(
            self.event_id,
            self.var_id,
            self.length,
        )

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "var"])
        assert s["event_type"] == EventType.LEN.value
        return LenEvent(*[s[p] for p in ["file", "line", "id", "var"]])

    def instantiate(self, var_id, length):
        return LenEvent(self.file, self.line, self.event_id, self.var, var_id, length)


class TestFunctionEvent(Event, ABC):
    def __init__(
        self,
        file: str,
        line: int,
        event_id: int,
        event_type: EventType,
        test: str,
        test_id: int,
    ):
        super().__init__(file, line, event_id, event_type)
        self.test = test
        self.test_id = test_id

    def serialize(self):
        default = super().serialize()
        default["test"] = self.test
        default["test_id"] = self.test_id
        return default


class TestStartEvent(TestFunctionEvent):
    def __init__(self, file: str, line: int, event_id: int, test: str, test_id: int):
        super().__init__(file, line, event_id, EventType.TEST_START, test, test_id)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},{self.test})"

    def handle(self, model: Any):
        model.handle_test_start_event(self)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "test", "test_id"])
        assert s["event_type"] == EventType.TEST_START.value
        return TestStartEvent(
            *[s[p] for p in ["file", "line", "id", "test", "test_id"]]
        )

    def instantiate(self):
        return TestStartEvent(
            self.file, self.line, self.event_id, self.test, self.test_id
        )


class TestEndEvent(TestFunctionEvent):
    def __init__(self, file: str, line: int, event_id: int, test: str, test_id: int):
        super().__init__(file, line, event_id, EventType.TEST_END, test, test_id)

    def __repr__(self):
        return f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},{self.test})"

    def handle(self, model: Any):
        model.handle_test_end_event(self)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "test", "test_id"])
        assert s["event_type"] == EventType.TEST_END.value
        return TestEndEvent(*[s[p] for p in ["file", "line", "id", "test", "test_id"]])

    def instantiate(self):
        return TestEndEvent(
            self.file, self.line, self.event_id, self.test, self.test_id
        )


class TestLineEvent(Event):
    def __init__(self, file: str, line: int, event_id: int):
        super().__init__(file, line, event_id, EventType.TEST_LINE)

    def handle(self, model: Any):
        model.handle_test_line_event(self)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id"])
        assert s["event_type"] == EventType.TEST_LINE.value
        return TestLineEvent(*[s[p] for p in ["file", "line", "id"]])

    def instantiate(self):
        return TestLineEvent(self.file, self.line, self.event_id)


class TestDefEvent(Event):
    def __init__(
        self,
        file,
        line: int,
        event_id: int,
        var: str,
        var_id: int = None,
    ):
        super().__init__(file, line, event_id, EventType.TEST_DEF)
        self.var = var
        self.var_id = var_id

    def __repr__(self):
        return (
            f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},"
            f"{self.var},{self.var_id})"
        )

    def handle(self, model: Any):
        model.handle_test_def_event(self)

    def serialize(self):
        default = super().serialize()
        default["var"] = self.var
        return default

    def dump(self):
        return encode_base_def_event(
            self.event_id,
            self.var_id,
        )

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "var"])
        assert s["event_type"] == EventType.TEST_DEF.value
        return TestDefEvent(*[s[p] for p in ["file", "line", "id", "var"]])

    def instantiate(
        self,
        var_id: int,
    ):
        return TestDefEvent(self.file, self.line, self.event_id, self.var, var_id)


class TestUseEvent(Event):
    def __init__(
        self, file: str, line: int, event_id: int, var: str, var_id: int = None
    ):
        super().__init__(file, line, event_id, EventType.TEST_USE)
        self.var = var
        self.var_id = var_id

    def __repr__(self):
        return f"{self.__class__.__name__}({self.file},{self.line},{self.event_id},{self.var},{self.var_id})"

    def handle(self, model: Any):
        model.handle_test_use_event(self)

    def serialize(self):
        default = super().serialize()
        default["var"] = self.var
        return default

    def dump(self):
        return encode_use_event(self.event_id, self.var_id)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id", "var"])
        assert s["event_type"] == EventType.TEST_USE.value
        return TestUseEvent(*[s[p] for p in ["file", "line", "id", "var"]])

    def instantiate(self, var_id):
        return TestUseEvent(self.file, self.line, self.event_id, self.var, var_id)


class TestAssertEvent(Event):
    def __init__(self, file: str, line: int, event_id: int):
        super().__init__(file, line, event_id, EventType.TEST_ASSERT)

    def handle(self, model: Any):
        model.handle_test_assert_event(self)

    @staticmethod
    def deserialize(s: dict):
        assert all(p in s for p in ["file", "line", "id"])
        assert s["event_type"] == EventType.TEST_ASSERT.value
        return TestAssertEvent(*[s[p] for p in ["file", "line", "id"]])

    def instantiate(self):
        return TestAssertEvent(self.file, self.line, self.event_id)


def serialize(event: Event):
    return event.serialize()


event_mapping = {
    EventType.LINE: LineEvent,
    EventType.BRANCH: BranchEvent,
    EventType.DEF: DefEvent,
    EventType.USE: UseEvent,
    EventType.FUNCTION_ENTER: FunctionEnterEvent,
    EventType.FUNCTION_EXIT: FunctionExitEvent,
    EventType.FUNCTION_ERROR: FunctionErrorEvent,
    EventType.LOOP_BEGIN: LoopBeginEvent,
    EventType.LOOP_HIT: LoopHitEvent,
    EventType.LOOP_END: LoopEndEvent,
    EventType.CONDITION: ConditionEvent,
    EventType.LEN: LenEvent,
    EventType.TEST_START: TestStartEvent,
    EventType.TEST_END: TestEndEvent,
    EventType.TEST_LINE: TestLineEvent,
    EventType.TEST_DEF: TestDefEvent,
    EventType.TEST_USE: TestUseEvent,
    EventType.TEST_ASSERT: TestAssertEvent,
}


def deserialize(s: dict):
    assert "event_type" in s
    type_ = EventType(s["event_type"])
    return event_mapping[type_].deserialize(s)


def dump(path: str, events: List[Event]):
    with open(path, "wb") as fp:
        for e in events:
            fp.write(e.dump())


def read_int(stream: BinaryIO, n: int, signed: bool = False) -> int:
    return int.from_bytes(stream.read(n), ENDIAN, signed=signed)


def read_len_str(stream: BinaryIO, n: int) -> str:
    length = read_int(stream, n)
    return stream.read(length).decode("utf8")


def read_len_bytes(stream: BinaryIO, n: int) -> bytes:
    length = read_int(stream, n)
    return stream.read(length)


def read_len_int(stream: BinaryIO, n: int, signed: bool = False) -> int:
    length = read_int(stream, n)
    return read_int(stream, length, signed=signed)


def load_event(e: bytes, base_events: Dict[int, Event]) -> Event:
    return load_next_event(io.BytesIO(e), base_events)


def load_next_event(stream: BinaryIO, events: Dict[int, Event]) -> Event:
    test = stream.read(1)
    if not test:
        raise ValueError("empty stream")
    event = events[read_int(stream, int.from_bytes(test, ENDIAN))]
    if event.event_type == EventType.DEF:
        # noinspection PyBroadException
        var_id = read_len_int(stream, 1)
        value = read_len_bytes(stream, 4)
        type_ = read_len_str(stream, 2)
        try:
            return event.instantiate(
                var_id,
                pickle.loads(value),
                type_,
            )
        except:
            value = value.decode("utf8")
            if value == "True":
                return event.instantiate(
                    var_id,
                    True,
                    type_,
                )
            elif value == "False":
                return event.instantiate(
                    var_id,
                    False,
                    type_,
                )
            else:
                return event.instantiate(
                    var_id,
                    None,
                    type_,
                )
    elif event.event_type == EventType.USE:
        var_id = read_len_int(stream, 1)
        return event.instantiate(var_id)
    elif event.event_type == EventType.FUNCTION_EXIT:
        # noinspection PyBroadException
        value = read_len_bytes(stream, 4)
        type_ = read_len_str(stream, 2)
        try:
            return event.instantiate(
                pickle.loads(value),
                type_,
            )
        except:
            value = value.decode("utf8")
            if value == "True":
                return event.instantiate(
                    True,
                    type_,
                )
            elif value == "False":
                return event.instantiate(
                    False,
                    type_,
                )
            else:
                return event.instantiate(
                    None,
                    type_,
                )
    elif event.event_type == EventType.CONDITION:
        value = bool(read_int(stream, 1))
        return event.instantiate(value)
    elif event.event_type == EventType.LEN:
        var_id = read_len_int(stream, 1)
        length = read_len_int(stream, 1)
        return event.instantiate(var_id, length)
    elif event.event_type == EventType.TEST_DEF:
        var_id = read_len_int(stream, 1)
        return event.instantiate(var_id)
    elif event.event_type == EventType.TEST_USE:
        var_id = read_len_int(stream, 1)
        return event.instantiate(var_id)
    else:
        return event.instantiate()


def load(path, base_events: Dict[int, Event]) -> List[Event]:
    events = list()
    with open(path, "rb") as fp:
        while True:
            try:
                events.append(load_next_event(fp, base_events))
            except:
                break
    return events


def load_json(path) -> Dict[int, Event]:
    with open(path, "r") as fp:
        events = json.load(fp)
    return {event.event_id: event for event in map(deserialize, events)}
