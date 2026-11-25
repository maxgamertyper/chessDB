import chess
from .enums import CompressionType

DEFAULT_FEN_NOTATION = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
STARTING_BYTE_SENTINEL = b"\x01"

class EncodingTable:
    def __init__(self, compression_type: CompressionType, game_end_senteinel: str = "GEnd"):
        self.moves = []
        self.game_count = 1
        self.game_end_sentinel = game_end_senteinel

        self.compression_type = compression_type

    def push_move(self, move: str):
        self.moves.append(move)

    def push_game_end(self):
        self.moves.append(self.game_end_sentinel)
        self.game_count += 1

    def get_raw_moves(self):
        return [move for move in self.moves if move != self.game_end_sentinel]

    def __len__(self):
        return len(self.moves)

    def __str__(self):
        return (
                f"[EncodingTable -> Sentinel: {self.game_end_sentinel}"
                f"; Games: {self.game_count}"
                f"; Moves: {len(self.moves)}; {self.moves}"
            )

class ChessEncoder:
    def __init__(self, data: bytearray, fen: str = DEFAULT_FEN_NOTATION, compression_type: CompressionType = CompressionType.MIXED_RADIX):
        self._board = chess.Board(fen)
        self._encode_data = STARTING_BYTE_SENTINEL + data

        self._bit_buffer = 0
        self._data_head = 0
        self._bits_in_buffer = 0
        self._bytes_in_array = len(self._encode_data)

        self._compression_type = compression_type
        self._remaining_quotient = int.from_bytes(self._encode_data, "big")

    def _get_next_data_byte(self):
        byte_data = self._encode_data[self._data_head]
        self._data_head += 1
        self._bytes_in_array -= 1
        return byte_data

    def _get_next_bits(self, bits: int):
        while self._bits_in_buffer < bits:
            if self._bytes_in_array > 0:
                next_byte = self._get_next_data_byte() & 0xFF
                self._bit_buffer |= next_byte << self._bits_in_buffer
                self._bits_in_buffer += 8
            else:
                self._bits_in_buffer = bits

        mask = (1 << bits) - 1
        output_int = self._bit_buffer & mask

        self._bit_buffer >>= bits
        self._bits_in_buffer -= bits

        return output_int

    def _get_legal_moves(self):
        sorted_moves = sorted(self._board.legal_moves, key=self._board.san)
        return [move.uci() for move in sorted_moves]

    def _get_next_move(self):
        legal_moves = self._get_legal_moves()

        if self._compression_type == CompressionType.BIT_CONCATENATION:
            usable_bits = len(legal_moves).bit_length() - 1
        
            eaten_bits = self._get_next_bits(usable_bits)
            return legal_moves[eaten_bits]
        
        elif self._compression_type == CompressionType.MIXED_RADIX:
            options = len(legal_moves)
            move_index = self._remaining_quotient % options
            self._remaining_quotient //= options

            return legal_moves[move_index]

    def _has_more_data(self):
        if self._compression_type == CompressionType.BIT_CONCATENATION:
            return self._bytes_in_array > 0 or self._bits_in_buffer > 0
        elif self._compression_type == CompressionType.MIXED_RADIX:
            return self._remaining_quotient > 0
        return False

    def calculateEncoding(self):
        table = EncodingTable(self._compression_type)

        while self._has_more_data():
            uci_move = self._get_next_move()
            self._board.push_uci(uci_move)
            table.push_move(uci_move)

            if (self._board.is_game_over(claim_draw = True) == True):
                table.push_game_end()
                self._board.reset()

        return table


class ChessDecoder:
        def __init__(self, table: EncodingTable, fen: str = DEFAULT_FEN_NOTATION):
            self._board = chess.Board(fen)
            self._encoded_table = table
            self._move_queue = table.get_raw_moves()

            self._bit_buffer = 0
            self._bits_in_buffer = 0

            self._compression_type = table.compression_type
            self._running_total = 0
            self._radix_base = 1

        def _get_next_move(self):
            return self._move_queue.pop(0)
    
        def _get_legal_moves(self):
            #this is going to sound weird but the san sorted produces less moves, but i need it in uci form
            sorted_moves = sorted(self._board.legal_moves, key=self._board.san)
            return [move.uci() for move in sorted_moves]
    
        def _decode_next_move(self):
            table_move = self._get_next_move()
            legal_moves = self._get_legal_moves()
            move_index = legal_moves.index(table_move)

            if self._compression_type == CompressionType.BIT_CONCATENATION:
                bit_count = len(legal_moves).bit_length() - 1

                if bit_count > 0:
                    self._bit_buffer |= (move_index & ((1 << bit_count) - 1)) << self._bits_in_buffer
                    self._bits_in_buffer += bit_count
                #this is then calculated in the main method to pull out bytes

            elif self._compression_type == CompressionType.MIXED_RADIX:
                legal_options = len(legal_moves)
                self._running_total += move_index * self._radix_base
                self._radix_base *= legal_options

            self._board.push_uci(table_move)

            if self._board.is_game_over(claim_draw=True):
                self._board.reset()


        def _pull_byte_from_buffer(self) -> int:
            byte_out = self._bit_buffer & 0xFF
            self._bit_buffer >>= 8
            self._bits_in_buffer -= 8
            return byte_out

        def decodeData(self) -> bytearray:
            ba = bytearray()

            while len(self._move_queue) > 0:
                self._decode_next_move()

                if self._compression_type == CompressionType.BIT_CONCATENATION:
                    while self._bits_in_buffer >= 8:
                        ba.append(self._pull_byte_from_buffer())

            if self._compression_type == CompressionType.MIXED_RADIX:
                byte_len = (self._running_total.bit_length() + 7) // 8
                ba = bytearray(self._running_total.to_bytes(byte_len, byteorder="big"))

            restored = bytearray(ba[1:])

            return restored
