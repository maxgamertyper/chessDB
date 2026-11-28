import chess, chess.pgn
import bisect
from datetime import date
from .enums import CompressionType
from . import headerInfo
import secrets
from itertools import groupby
import math

DEFAULT_FEN_NOTATION = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
STARTING_BYTE_SENTINEL = b"\x01"

class EncodingTable:
    def __init__(self, compression_type: CompressionType, game_end_senteinel: str = "GEnd"):
        self.moves = []
        self.game_count = 1
        self.game_end_sentinel = game_end_senteinel
        self.id = secrets.token_hex(8)
        self._game_indexes = []
        # this is technically "1-indexed" really it just labels the end of each game

        self.compression_type = compression_type

    def push_move(self, move: str):
        self.moves.append(move)

    def push_game_end(self):
        self.moves.append(self.game_end_sentinel)
        self.game_count += 1
        self._game_indexes.append(len(self.moves))

    def get_raw_moves(self):
        return self.moves

    def _make_nice_pgn(self, board, game_number):
        game = chess.pgn.Game.from_board(board)
        game.headers["Event"] = f"Chess-Stenography {self.id}"
        game.headers["Site"] = "https://github.com/maxgamertyper/chessDB"
        game.headers["Date"] = date.today().strftime("%Y.%m.%d")
        game.headers["Round"] = game_number
        game.headers["White"] = "Hermes"
        game.headers["Black"] = "Sphinx"
        return str(game)

    def to_pgns(self):
        board = chess.Board()
        game_pgns = []

        for move in self.moves:
            if move==self.game_end_sentinel:
                game_pgns.append(self._make_nice_pgn(board, len(game_pgns)))
                board.reset()
                continue
            board.push_uci(move)

        if board.move_stack:
            game_pgns.append(self._make_nice_pgn(board, len(game_pgns)))

        return game_pgns

    def _get_starting_pgn_length(self):
        empty_table = EncodingTable(self.compression_type,self.game_end_sentinel)
        pgn = empty_table.combined_pgn()

        return len(pgn.encode("utf-8"))

    def get_game_bounds(self, size: int, moves: int):
        estimated_overhead_per_move = 6
        # this is for extra periods, spaces, numbers, etc that happen when doing a pgn
        running_count = self._get_starting_pgn_length()
        running_moves = 0
        current_start = 1
        game_number = 1
        game_bounds = []
        current_game_size = 0
        current_move_count = 0

        for move in self.moves:
            if move == self.game_end_sentinel:
                running_count += current_game_size
                running_moves += current_move_count
                
                if running_count > size or running_moves > moves:
                    game_bounds.append((current_start, game_number - 1))
                    current_start = game_number
                    running_count = current_game_size + self._get_starting_pgn_length()
                    running_moves = current_move_count

                game_number += 1
                current_game_size = 0
                current_move_count = 0

            move_size = len(move.encode("utf-8"))
            current_move_count+=1
            current_game_size += move_size + estimated_overhead_per_move

        if current_start < game_number:
            game_bounds.append((current_start, game_number - 1))

        return game_bounds

    def combined_pgn(self, first_game: int = -1, last_game: int = math.inf):
        master_game = chess.pgn.Game()
        board = chess.Board()

        master_game.headers["Event"] = f"Chess-Stenography {self.id}"
        master_game.headers["Site"] = "https://github.com/maxgamertyper/chessDB"
        master_game.headers["Date"] = date.today().strftime("%Y.%m.%d")
        master_game.headers["Round"] = 0
        master_game.headers["White"] = "Hermes"
        master_game.headers["Black"] = "Sphinx"

        def flush_board():
            if not board.move_stack:
                return
            node = master_game
            for stack_move in board.move_stack:
                if node.has_variation(stack_move):
                    node = node.variation(stack_move)
                else:
                    node = node.add_variation(stack_move)
            board.reset()

        start = self._game_indexes[first_game - 2] if first_game > 1 else 0
        game_number = first_game

        for i in range(start,len(self.moves)):
            move = self.moves[i]
            if move == self.game_end_sentinel:
                flush_board()
                game_number += 1
                if game_number > last_game:
                    break
                continue
            board.push_uci(move)

        flush_board()

        return str(master_game)

    def split_games(self):
        games = [
            list(group)
            for is_sentinel, group in groupby(
                self.moves, key=lambda m: m == self.game_end_sentinel
            )
            if not is_sentinel
        ]
        return games


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
    def __init__(self, data: bytes, fen: str = DEFAULT_FEN_NOTATION, compression_type: CompressionType = CompressionType.MIXED_RADIX, include_metadata: bool = True):
        self._board = chess.Board(fen)
        self._encode_data = STARTING_BYTE_SENTINEL + data
        self._include_metadata = include_metadata

        self._bit_buffer = 0
        self._data_head = 0
        self._bits_in_buffer = 0
        self._bytes_in_array = len(self._encode_data)

        if compression_type == CompressionType.UNDETERMINED:
            compression_type = CompressionType.MIXED_RADIX # the middle ground for speed and compressibility
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
            if usable_bits == 0:
                return legal_moves[0]
        
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

    def _add_metadata_to_board(self, game_number: int, table):
        compression_move = headerInfo.COMPRESSION_TO_HEADER_MOVE[self._compression_type]
        self._board.push_uci(compression_move)
        table.push_move(compression_move)

        #game number
        seq = game_number - 1
        for _ in range(headerInfo.GAME_NUMBER_SEQUENCE_PLIES):
            legal_moves = self._get_legal_moves() 
            seq, move_index = divmod(seq, len(legal_moves))
            move = legal_moves[move_index]
            self._board.push_uci(move)
            table.push_move(move)

    def _has_more_data(self):
        if self._compression_type == CompressionType.BIT_PACKING:
            return self._bytes_in_array > 0 or self._bits_in_buffer > 0
        elif self._compression_type == CompressionType.MIXED_RADIX or self._compression_type == CompressionType.WEIGHTED_ARITHMETIC:
            return self._remaining_quotient > 0
        return False

    def calculateEncoding(self):
        table = EncodingTable(self._compression_type)
        game_number = 1
        self._add_metadata_to_board(1, table)

        while self._has_more_data():
            uci_move = self._get_next_move()
            self._board.push_uci(uci_move)
            table.push_move(uci_move)

            if (self._board.is_game_over(claim_draw = True) == True):
                table.push_game_end()
                self._board.reset()
                game_number += 1
                self._add_metadata_to_board(game_number, table)

        return table


class ChessDecoder:
    def __init__(self, table: EncodingTable, fen: str = DEFAULT_FEN_NOTATION):
        self._board = chess.Board(fen)
        self._encoded_table = table
        self._move_queue = []

        self._bit_buffer = 0
        self._bits_in_buffer = 0

        self._compression_type = table.compression_type
        self._running_total = 0
        self._radix_base = 1

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

        if table_move == self._encoded_table.game_end_sentinel:
            self._board.reset()
            self._skip_game_header()
            return

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
            
            if len(self._move_queue) == 1:
                self._running_total = move_index
            else:
                weighted_table, total_weight = self._build_weighted_table(legal_moves)
                _, start, _, weight = weighted_table[move_index]
                self._weighted_history.append((start, weight, total_weight))

        self._board.push_uci(table_move)

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

    def _decode_metadata(self):
        games = self._encoded_table.split_games()
        ordered_games = {}

        for game in games:
            game_moves = list(game)
            game_number = self._decode_game_meta(game)
            if game_number in ordered_games:
                raise ValueError(f"Duplicate game sequence number found: {game_number}")

            ordered_games[game_number] = game_moves

        expected_numbers = set(range(1, len(games) + 1))
        if set(ordered_games.keys()) != expected_numbers:
            missing = sorted(expected_numbers - set(ordered_games.keys()))
            raise ValueError(f"Missing game(s) in sequence: {missing}")

        sentinel = self._encoded_table.game_end_sentinel
        self._move_queue = []

        for game_num in sorted(ordered_games.keys()):
            self._move_queue.extend(ordered_games[game_num])
            self._move_queue.append(sentinel)

    def _skip_game_header(self):
        if len(self._move_queue) == 0: return
        for _ in range(1 + headerInfo.GAME_NUMBER_SEQUENCE_PLIES):
            header_move = self._move_queue.pop(0)
            self._board.push_uci(header_move)

    def _decode_game_meta(self, game):
        self._board.reset()
        game_number = 0

        #first ply
        w1_move = game.pop(0)
        if w1_move not in headerInfo.HEADER_MOVE_TO_COMPRESSION:
            raise ValueError(f"Unrecognized compression header move: {w1_move}")

        compression_type = headerInfo.HEADER_MOVE_TO_COMPRESSION[w1_move]
        if self._compression_type == CompressionType.UNDETERMINED:
            self._compression_type = compression_type
        elif compression_type != self._compression_type:
            raise ValueError(
                f"Compression type mismatch: got {compression_type.name}, "
                f"expected {self._compression_type.name}"
            )

        self._board.push_uci(w1_move)
        radix = 1

        for _ in range(headerInfo.GAME_NUMBER_SEQUENCE_PLIES):
            move = game.pop(0)
            legal_moves = self._get_legal_moves()
            move_index = legal_moves.index(move)
            self._board.push_uci(move)
            
            game_number += move_index * radix
            radix *= len(legal_moves)

        self._board.reset()
        return game_number+1

    def decodeData(self) -> bytearray:
        self._decode_metadata()
        self._skip_game_header()
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

        return bytes(restored)