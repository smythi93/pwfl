from typing import Union, Any

ENDIAN = "big"


def get_byte_length(x: Union[int, float]):
    return max((x.bit_length() + 7) // 8, 1)


def encode_event(event_id: int):
    len_id = get_byte_length(event_id)
    return b"".join(
        [
            len_id.to_bytes(1, ENDIAN),
            event_id.to_bytes(len_id, ENDIAN),
        ]
    )


def encode_base_def_event(
    event_id: int,
    var_id: int,
):
    len_var_id = get_byte_length(var_id)
    return encode_event(event_id) + b"".join(
        [
            len_var_id.to_bytes(1, ENDIAN),
            var_id.to_bytes(len_var_id, ENDIAN),
        ]
    )


def encode_def_event(
    event_id: int,
    var_id: int,
    value: Any,
    type_: str,
):
    if isinstance(value, bytes):
        value = value
    else:
        value = str(value).encode("utf8")
    len_value = len(value)
    len_type = len(type_)
    return encode_base_def_event(event_id, var_id) + b"".join(
        [
            len_value.to_bytes(4, ENDIAN),
            value,
            len_type.to_bytes(2, ENDIAN),
            type_.encode("utf8"),
        ]
    )


def encode_function_exit_event(
    event_id: int,
    return_value: Any,
    type_: str,
):
    if isinstance(return_value, bytes):
        value = return_value
    else:
        value = str(return_value).encode("utf8")
    len_value = len(value)
    len_type = len(type_)
    return encode_event(event_id) + b"".join(
        [
            len_value.to_bytes(4, ENDIAN),
            value,
            len_type.to_bytes(2, ENDIAN),
            type_.encode("utf8"),
        ]
    )


def encode_condition_event(
    event_id: int,
    value: any,
):
    return encode_event(event_id) + b"".join(
        [
            (1 if value else 0).to_bytes(1, ENDIAN),
        ]
    )


def encode_use_event(
    event_id: int,
    var_id: int,
):
    len_var_id = get_byte_length(var_id)
    return encode_event(event_id) + b"".join(
        [
            len_var_id.to_bytes(1, ENDIAN),
            var_id.to_bytes(len_var_id, ENDIAN),
        ]
    )


def encode_len_event(
    event_id: int,
    var_id: int,
    length: int,
):
    len_var_id = get_byte_length(var_id)
    len_length = get_byte_length(length)
    return encode_event(event_id) + b"".join(
        [
            len_var_id.to_bytes(1, ENDIAN),
            var_id.to_bytes(len_var_id, ENDIAN),
            len_length.to_bytes(1, ENDIAN),
            length.to_bytes(len_length, ENDIAN),
        ]
    )
