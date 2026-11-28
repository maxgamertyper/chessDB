import berserk
from . import codec, headerInfo, enums
import chess.pgn
import io

class LichessBot:
    def __init__(self, token: str, studyID: str):
        self._session = berserk.TokenSession(token)
        self._client = berserk.Client(session=self._session)
        self._study_id = studyID

    def upload_table(self, encodingTable: codec.EncodingTable, chapter_name: str = None):
        splits = encodingTable.get_game_bounds(50000, 3000) # split games by ~50kb pgn files or 3000 moves
        chapters = []
        split_number = 1

        for start_game, end_game in splits:
            link = self._upload_individual(
                encodingTable, 
                start_game, 
                end_game, 
                f"{chapter_name} (split: {split_number})"
            )
            chapters.append(link)
            split_number += 1

        return chapters


    def _upload_individual(self, encodingTable, start, end, chapter_name):
        if chapter_name == None: chapter_name = encodingTable.id
        comb_pgn = encodingTable.combined_pgn(start, end)

        try:
            links = self._client.studies.import_pgn(
                study_id=self._study_id,
                chapter_name=chapter_name,
                pgn=comb_pgn
            )
            print(links)
        except berserk.exceptions.ResponseError as e:
            print(f"Lichess API Error: {e}")
        print("There needs to be some checks here, but it works for now")
        return f"https://lichess.org/study/{self._study_id}/{links[0]["id"]}"

    def read_chapter(self, chapter_id: str):
        pgn = self._client.studies.export_chapter(self._study_id, chapter_id)
        pgn_stream = io.StringIO(pgn)
        read_game = chess.pgn.read_game(pgn_stream)

        games = self._flatten_game_pgn(read_game)
        table = codec.EncodingTable(enums.CompressionType.UNDETERMINED)

        for i, move_path in enumerate(games):
            for move in move_path:
                table.push_move(move.uci())

            if i < len(games) - 1:
                table.push_game_end()

        return table

    def read_chapters(self, chapter_ids):
        chapter_games = []

        for chapter_id in chapter_ids:
            pgn = self._client.studies.export_chapter(self._study_id, chapter_id)
            pgn_stream = io.StringIO(pgn)
            chapter_games.append(chess.pgn.read_game(pgn_stream))

        all_lines = self._flatten_game_pgns(chapter_games)
        table = codec.EncodingTable(enums.CompressionType.UNDETERMINED)
        
        for i, move_path in enumerate(all_lines):
            for move in move_path:
                table.push_move(move.uci())

            if i < len(all_lines) - 1:
                table.push_game_end()

        return table


    def _flatten_game_pgns(self, games):
        total_lines = []

        for game in games:
            total_lines.extend(self._flatten_game_pgn(game))

        return total_lines

    def _flatten_game_pgn(self, game: chess.pgn.Game) -> list[list[chess.Move]]:
        lines = []
        stack = [(game, [])]

        while stack:
            node, move_path = stack.pop()

            if not node.variations:
                lines.append(move_path)
                continue

            for child in reversed(node.variations):
                stack.append((child, move_path + [child.move]))

        return lines

