import struct
from core.structData import DataTypeStructId

class BinaryWriter():
    def __init__(self):
        self._buffer = bytearray()

    def _write(self, value, valueType, be=True, valueSize=None, valueIdentifier=None):
        valueIdentifier = DataTypeStructId[valueType].value

        # Add structured bytes to buffer
        self._buffer.extend(struct.pack(f"{">" if be else "<"}{valueSize if valueIdentifier==DataTypeStructId["string_t"].value else ""}{valueIdentifier}", value))

    # Write methods
    def writeBool(self, value:bool): self._write(value, "bool_t")
    def writeI8(self, value:int): self._write(value, "i8_t")
    def writeU8(self, value:int): self._write(value, "u8_t")
    def writeI16(self, value:int, be=True): self._write(value, "i16_t", be=be)
    def writeU16(self, value:int, be=True): self._write(value, "u16_t", be=be)
    def writeI32(self, value:int, be=True): self._write(value, "i32_t", be=be)
    def writeU32(self, value:int, be=True): self._write(value, "u32_t", be=be)
    def writeI64(self, value:int, be=True): self._write(value, "i64_t", be=be)
    def writeU64(self, value:int, be=True): self._write(value, "u64_t", be=be)
    def writeFloat(self, value:float, be=True): self._write(value, "float_t", be=be)
    def writeDouble(self, value:float, be=True): self._write(value, "double_t", be=be)
    def writeChar(self, value:str, be=True): self._write(value, "char_t", be=be)
    def writeStringAsciiFixed(self, value:str, be=True): self._write(value, "string_t", be=be, valueSize=len(value))

    def writeStringUtf16(self, value:str) -> None:
        # Convert value to UTF16 bytes
        encodedString = value.encode("utf-16-be")

        # Store number of characters in string which goes before that many UTF-16BE code units
        length = len(encodedString)

        self.writeU16(length)
        self._buffer.extend(encodedString)

    @property
    def buffer(self) -> bytearray:
        return self._buffer