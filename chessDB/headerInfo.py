from .enums import CompressionType

GAME_NUMBER_SEQUENCE_PLIES = 3

COMPRESSION_TO_HEADER_MOVE: dict[CompressionType, str] = {
    CompressionType.MIXED_RADIX: "e2e4",
    CompressionType.BIT_PACKING: "c2c4",
    CompressionType.WEIGHTED_ARITHMETIC: "d2d3",
}

HEADER_MOVE_TO_COMPRESSION: dict[str, CompressionType] = {
    move: c_type for c_type, move in COMPRESSION_TO_HEADER_MOVE.items()
}