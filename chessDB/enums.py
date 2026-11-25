from enum import IntEnum, auto

class CompressionType(IntEnum):
    BIT_PACKING = auto()
    MIXED_RADIX = auto()
    WEIGHTED_ARITHMETIC = auto()