from abc import abstractmethod, ABC
from enum import IntEnum
from core.BinaryWriter import BinaryWriter
from core.BinaryReader import BinaryReader

# Truncate / extend string to specific length
def extendString(string, length):
    return string[:length].ljust(length)

class PacketId(IntEnum):
    keepAlive = 0
    login = 1
    preLogin = 2

class Packet(ABC):
    def __init__(self):
        self.buffer = bytearray()

    @abstractmethod
    def encode(self, writer:BinaryWriter): pass

    @abstractmethod
    def decode(self, reader:BinaryReader): pass