import sys


sys.path = sys.path[1:] + sys.path[:1]
import atexit
import os
import pickle
from typing import Any

sys.path = sys.path[-1:] + sys.path[:-1]

from sflkitlib.events import codec

_event_path_file = open(os.getenv("EVENTS_PATH", default="EVENTS_PATH"), "wb")


def reset():
    # noinspection PyBroadException
    try:
        dump_events()
    except:
        pass
    global _event_path_file
    _event_path_file = open(os.getenv("EVENTS_PATH", default="EVENTS_PATH"), "wb")


def get_id(x: Any):
    try:
        return id(x)
    except (AttributeError, TypeError):
        return None


def get_type(x: Any):
    try:
        return type(x)
    except (AttributeError, TypeError):
        return None


def dump_events():
    try:
        _event_path_file.flush()
        _event_path_file.close()
    except:
        pass


def write(encoded_event: bytes):
    global _event_path_file
    try:
        _event_path_file.write(encoded_event)
    except ValueError:
        pass


atexit.register(dump_events)


def add_line_event(event_id: int):
    write(codec.encode_event(event_id))


def add_branch_event(event_id: int):
    write(codec.encode_event(event_id))


def add_def_event(event_id: int, var_id: int, value: Any, type_: type):
    if var_id is not None:
        if type_ in [int, float, complex, str, bytes, bytearray, bool] or value is None:
            write(
                codec.encode_def_event(
                    event_id,
                    var_id,
                    pickle.dumps(value),
                    type_.__name__,
                )
            )
        else:
            write(
                codec.encode_def_event(
                    event_id,
                    var_id,
                    pickle.dumps(None),
                    f"{type_.__module__}.{type_.__name__}",
                )
            )


def add_function_enter_event(event_id: int):
    write(codec.encode_event(event_id))


def add_function_exit_event(
    event_id: int,
    return_value: Any,
    type_: type,
):
    if (
        type_ in [int, float, complex, str, bytes, bytearray, bool]
        or return_value is None
    ):
        write(
            codec.encode_function_exit_event(
                event_id,
                pickle.dumps(return_value),
                type_.__name__,
            )
        )
    else:
        # noinspection PyBroadException
        try:
            write(
                codec.encode_function_exit_event(
                    event_id,
                    pickle.dumps(bool(return_value)),
                    f"{type_.__module__}.{type_.__name__}",
                )
            )
        except:
            write(
                codec.encode_function_exit_event(
                    event_id,
                    pickle.dumps(None),
                    f"{type_.__module__}.{type_.__name__}",
                )
            )


def add_function_error_event(event_id: int):
    write(codec.encode_event(event_id))


def add_condition_event(event_id: int, value: Any):
    if value:
        write(codec.encode_condition_event(event_id, True))
    else:
        write(codec.encode_condition_event(event_id, False))


def add_loop_begin_event(event_id: int):
    write(codec.encode_event(event_id))


def add_loop_hit_event(event_id: int):
    write(codec.encode_event(event_id))


def add_loop_end_event(event_id: int):
    write(codec.encode_event(event_id))


def add_use_event(event_id: int, var_id: int):
    if var_id is not None:
        write(codec.encode_use_event(event_id, var_id))


def add_len_event(event_id: int, var_id: int, length: int):
    if var_id is not None:
        write(codec.encode_len_event(event_id, var_id, length))


def add_test_start_event(event_id: int):
    write(codec.encode_event(event_id))


def add_test_end_event(event_id: int):
    write(codec.encode_event(event_id))


def add_test_line_event(event_id: int):
    write(codec.encode_event(event_id))


def add_test_def_event(event_id: int, var_id: int):
    if var_id is not None:
        write(codec.encode_base_def_event(event_id, var_id))


def add_test_use_event(event_id: int, var_id: int):
    if var_id is not None:
        write(codec.encode_use_event(event_id, var_id))


def add_test_assert_event(event_id: int):
    write(codec.encode_event(event_id))
