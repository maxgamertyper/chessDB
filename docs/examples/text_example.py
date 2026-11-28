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
    encoder = ChessEncoder(encodearray, compression_type=CompressionType.BIT_PACKING)

    table = encoder.calculateEncoding()

    chapter_link = bot.upload_table(table, chapter_name)
    print(chapter_link)
    return chapter_link


def read_chapter(study_id):
    read_table = bot.read_chapter(study_id)

    decoder = ChessDecoder(read_table)
    out_data = decoder.decodeData()
    print(out_data)
    return out_data

if __name__ == "__main__":
    #upload_chapter(b"According to all known laws of aviation, there is no way a bee should be able to fly. Its wings are too small to get its fat little body off the ground. The bee, of course, flies anyway, because bees don't care what humans think is impossible.", "beeBIT")
    #read_chapter("{USE THE LINK TO CHECK THE CHAPTER ID}")
    pass