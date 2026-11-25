import chess, chess.pgn
import bisect
from datetime import date
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

    def _make_nice_pgn(self, board, game_number):
        game = chess.pgn.Game.from_board(board)
        game.headers["Event"] = f"Chess-Stenography"
        game.headers["Site"] = "https://github.com/maxgamertyper/chessDB"
        game.headers["Date"] = date.today().strftime("%Y.%m.%d")
        game.headers["Round"] = game_number
        game.headers["White"] = "Hermes"
        game.headers["Black"] = "Sphinx"
        return str(game)


    def to_pgn(self):
        board = chess.Board()
        game_pgns = []

        for move in self.moves:
            if move==self.game_end_sentinel:
                game_pgns.append()
                board.reset()
                continue
            board.push_uci(move)

        if board.move_stack:
            game_pgns.append(self._make_nice_pgn(board, len(game_pgns)))

        return game_pgns


    def __len__(self):
        return len(self.moves)

    def __str__(self):
        return (
                f"[EncodingTable -> Sentinel: {self.game_end_sentinel}"
                f"; Type: {self.compression_type.name}"
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
        #used for radix_mixed and weighted_average
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

    def _count_legal_moves(self):
        return self._board.legal_moves.count()

    def _build_weighted_table(
        self, legal_moves: list[str]
    ) -> tuple[list[tuple[str, int, int]], int]:
        weighted_table = []
        total_weight = 0

        for move in legal_moves:
            self._board.push_uci(move)
            weight = max(1, self._count_legal_moves())
            self._board.pop()

            start = total_weight
            total_weight += weight
            weighted_table.append((move, start, weight))

        return weighted_table, total_weight

    def _get_next_move(self):
        legal_moves = self._get_legal_moves()

        if self._compression_type == CompressionType.BIT_PACKING:
            usable_bits = self._count_legal_moves().bit_length() - 1
        
            eaten_bits = self._get_next_bits(usable_bits)
            return legal_moves[eaten_bits]
        
        elif self._compression_type == CompressionType.MIXED_RADIX:
            options = self._count_legal_moves()
            move_index = self._remaining_quotient % options
            self._remaining_quotient //= options

            return legal_moves[move_index]

        elif self._compression_type == CompressionType.WEIGHTED_ARITHMETIC:

            if self._remaining_quotient < self._count_legal_moves():
                move = legal_moves[self._remaining_quotient]
                self._remaining_quotient = 0
                return move

            weighted_table, total_weight = self._build_weighted_table(legal_moves)

            new_quotient, mod = divmod(self._remaining_quotient, total_weight)
            tuple_index = bisect.bisect_right(weighted_table, mod,
                    key= lambda move_tuple: move_tuple[1] + move_tuple[2])
            move, start, weight = weighted_table[tuple_index]

            self._remaining_quotient = new_quotient * weight + (mod - start)
            return move

    def _has_more_data(self):
        if self._compression_type == CompressionType.BIT_PACKING:
            return self._bytes_in_array > 0 or self._bits_in_buffer > 0
        elif self._compression_type == CompressionType.MIXED_RADIX or self._compression_type == CompressionType.WEIGHTED_ARITHMETIC:
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

            self._is_first_decode = True
            self._weighted_history = []

        def _get_next_move(self):
            return self._move_queue.pop(0)
    
        def _get_legal_moves(self):
            #this is going to sound weird but the san sorted produces less moves, but i need it in uci form
            sorted_moves = sorted(self._board.legal_moves, key=self._board.san)
            return [move.uci() for move in sorted_moves]

        def _count_legal_moves(self):
            return self._board.legal_moves.count()
    
        def _decode_next_move(self):
            table_move = self._get_next_move()
            legal_moves = self._get_legal_moves()
            move_index = legal_moves.index(table_move)

            if self._compression_type == CompressionType.BIT_PACKING:
                bit_count = self._count_legal_moves().bit_length() - 1

                if bit_count > 0:
                    self._bit_buffer |= (move_index & ((1 << bit_count) - 1)) << self._bits_in_buffer
                    self._bits_in_buffer += bit_count
                #this is then calculated in the main method to pull out bytes

            elif self._compression_type == CompressionType.MIXED_RADIX:
                legal_options = self._count_legal_moves()
                self._running_total += move_index * self._radix_base
                self._radix_base *= legal_options

            elif self._compression_type == CompressionType.WEIGHTED_ARITHMETIC:
                
                if len(self._move_queue) == 0:
                    self._running_total = move_index
                else:
                    weighted_table, total_weight = self._build_weighted_table(legal_moves)
                    _, start, _, weight = weighted_table[move_index]
                    self._weighted_history.append((start, weight, total_weight))


            self._board.push_uci(table_move)

            if self._board.is_game_over(claim_draw=True):
                self._board.reset()

        def _build_weighted_table(
            self, legal_moves: list[str]
        ) -> tuple[list[tuple[str, int, int, int]], int]:
            weighted_table = []
            total_weight = 0

            for move in legal_moves:
                self._board.push_uci(move)
                weight = max(1, self._count_legal_moves())
                self._board.pop()

                start = total_weight
                total_weight += weight
                weighted_table.append((move, start, total_weight, weight))

            return weighted_table, total_weight

        def _pull_byte_from_buffer(self) -> int:
            byte_out = self._bit_buffer & 0xFF
            self._bit_buffer >>= 8
            self._bits_in_buffer -= 8
            return byte_out

        def decodeData(self) -> bytearray:
            ba = bytearray()

            while len(self._move_queue) > 0:
                self._decode_next_move()

                if self._compression_type == CompressionType.BIT_PACKING:
                    while self._bits_in_buffer >= 8:
                        ba.append(self._pull_byte_from_buffer())

            if self._compression_type == CompressionType.WEIGHTED_ARITHMETIC:
                for start, weight, total_weight in reversed(self._weighted_history):
                    new_q, offset = divmod(self._running_total, weight)
                    self._running_total = new_q * total_weight + start + offset

            if self._compression_type == CompressionType.MIXED_RADIX or self._compression_type == CompressionType.WEIGHTED_ARITHMETIC:
                byte_len = (self._running_total.bit_length() + 7) // 8
                ba = bytearray(self._running_total.to_bytes(byte_len, byteorder="big"))

            restored = bytearray(ba[1:])

            return restored