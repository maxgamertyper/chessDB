from chessDB.codec import ChessEncoder, ChessDecoder
from chessDB.enums import CompressionType

if __name__ == "__main__":
    data_to_encode = bytearray(b"Max")
    print(data_to_encode.decode("utf-8"))
    encoder = ChessEncoder(data_to_encode, compression_type=CompressionType.BIT_CONCATENATION)

    table = encoder.calculateEncoding()
    print(table)

    decoder = ChessDecoder(table)
    out_data = decoder.decodeData()

    print(out_data.decode("utf-8"))
