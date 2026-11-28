from chessDB.codec import ChessEncoder, ChessDecoder
from chessDB.enums import CompressionType
from chessDB.lichess import LichessBot
import os
from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("BOT_TOKEN")
study_key = os.getenv("STUDY_KEY") #idk if this is bad to show or not
bot = LichessBot(bot_token, study_key)

def upload_chapter(encodearray, chapter_name):
    encoder = ChessEncoder(encodearray, compression_type=CompressionType.MIXED_RADIX)

    table = encoder.calculateEncoding()

    chapter_links = bot.upload_table(table, chapter_name)
    print(chapter_links)


def read_chapter(chapter_id):
    read_table = bot.read_chapter(chapter_id)

    decoder = ChessDecoder(read_table)
    out_data = decoder.decodeData()
    print(out_data)
    return out_data

def read_chapters(chapter_ids):
    read_table = bot.read_chapters(chapter_ids)

    decoder = ChessDecoder(read_table)
    return decoder.decodeData()

def read_file(file_name):
    encode_data = None
    with open(file_name, "rb") as f:
        encode_data = f.read()
    return encode_data

def to_file(file_name, data):
    with open (file_name, "wb") as f:
        f.write(data)

if __name__ == "__main__":

    #upload_chapter(read_file("signature.png"), "signature")
    #to_file(
    #    "output.txt",
    #    read_chapter("{YOUR CHAPTER ID HERE}")
    #)
    #to_file(
    #    "output.png",
    #    read_chapters(["CHAPTER 1", "CHAPTER 2"])
    #)
    pass