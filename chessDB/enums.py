from enum import IntEnum, auto

class CompressionType(IntEnum):
    BIT_CONCATENATION = auto()
    MIXED_RADIX = auto()