from enum import Enum

class DataTypeSizes(Enum):
    bool_t = 1
    i8_t = 1
    u8_t = 1
    i16_t = 2
    u16_t = 2
    i32_t = 4
    u32_t = 4
    i64_t = 8
    u64_t = 8
    float_t = 4
    double_t = 8
    char = 1

class DataTypeStructId(Enum):
    bool_t = "?"
    i8_t = "b"
    u8_t = "B"
    i16_t = "h"
    u16_t = "H"
    i32_t = "i"
    u32_t = "I"
    i64_t = "q"
    u64_t = "Q"
    float_t = "f"
    double_t = "d"
    char_t = "c"
    string_t = "s"