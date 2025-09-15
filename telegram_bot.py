import asyncio
from aiogram.types import Message
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from Secret.key import bot_key
import datetime
import os
import csv
import uuid
from functools import wraps
import re
import aiohttp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import lyricsgenius

if not os.path.exists('logs'):
    os.makedirs('logs')

CSV_LOG_FILE = 'logs/bot_logs.csv'
if not os.path.exists(CSV_LOG_FILE):
    with open(CSV_LOG_FILE, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['unic_id', '@TG_NICK', 'Motion', 'API', 'Date', 'Time', 'API_answer']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

def log_to_csv(motion, api_used="NONE", api_answer="NONE"):
    def decorator(func):
        @wraps(func)
        async def wrapper(message: Message, *args, **kwargs):
            user = message.from_user
            unic_id = str(uuid.uuid4())
            tg_nick = user.username or user.first_name
            current_date = datetime.datetime.now().strftime("%Y-%m-%d")
            current_time = datetime.datetime.now().strftime("%H:%M:%S")
            
            if motion == "Keyboard typing":
                api_used_final = "NONE"
                api_answer_final = "NONE"
            else:
                api_used_final = api_used
                api_answer_final = api_answer
            
            with open(CSV_LOG_FILE, 'a', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['unic_id', '@TG_NICK', 'Motion', 'API', 'Date', 'Time', 'API_answer']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writerow({
                    'unic_id': unic_id,
                    '@TG_NICK': tg_nick,
                    'Motion': motion,
                    'API': api_used_final,
                    'Date': current_date,
                    'Time': current_time,
                    'API_answer': api_answer_final
                })
            
            return await func(message, *args, **kwargs)
        return wrapper
    return decorator

TELEGRAM_TOKEN = bot_key['BOT_API_TOKEN']
SPOTIFY_CLIENT_ID = bot_key['SPOTIFY_CLIENT_ID']
SPOTIFY_CLIENT_SECRET = bot_key['SPOTIFY_CLIENT_SECRET']
YOUTUBE_API_KEY = bot_key['YOUTUBE_API_KEY']
GENIUS_ACCESS_TOKEN = bot_key['GENIUS_ACCESS_TOKEN']

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

genius = lyricsgenius.Genius(GENIUS_ACCESS_TOKEN)
genius.verbose = False
genius.remove_section_headers = True

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(bot=bot)

def escape_markdown(text):
    if not text:
        return ""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', str(text))

async def safe_send_message(chat_id, text, parse_mode=None, **kwargs):
    try:
        if len(text) > 4096:
            text = text[:4090] + "..."
            
        if parse_mode == 'Markdown':
            text = escape_markdown(text)
            
        await bot.send_message(chat_id, text, parse_mode=parse_mode, **kwargs)
        return True
    except Exception as e:
        try:
            clean_text = re.sub(r'[*_`\[\]()~>#+-=|{}.!]', '', text)
            if len(clean_text) > 4096:
                clean_text = clean_text[:4090] + "..."
            await bot.send_message(chat_id, clean_text, **kwargs)
            return True
        except Exception as e2:
            await bot.send_message(chat_id, "Произошла ошибка при отправке сообщения")
            return False

async def search_spotify_tracks(query, limit=1):
    try:
        results = sp.search(q=query, type='track', limit=limit)
        return [{
            'name': item['name'],
            'artist': item['artists'][0]['name'],
            'album': item['album']['name'],
            'url': item['external_urls']['spotify'],
            'image_url': item['album']['images'][0]['url'] if item['album']['images'] else None
        } for item in results['tracks']['items']]
    except Exception as e:
        return []

async def search_spotify_albums(query, limit=1):
    try:
        results = sp.search(q=query, type='album', limit=limit)
        return [{
            'name': item['name'],
            'artist': item['artists'][0]['name'],
            'url': item['external_urls']['spotify'],
            'image_url': item['images'][0]['url'] if item['images'] else None,
            'release_date': item['release_date']
        } for item in results['albums']['items']]
    except Exception as e:
        return []

async def search_youtube_videos(query, limit=5):
    try:
        search_url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            'part': 'snippet',
            'q': query,
            'type': 'video',
            'maxResults': limit,
            'key': YOUTUBE_API_KEY
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    videos = []
                    for item in data.get('items', []):
                        video_id = item['id']['videoId']
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        
                        video = {
                            'title': item['snippet']['title'],
                            'channel': item['snippet']['channelTitle'],
                            'url': video_url,
                            'thumbnail': item['snippet']['thumbnails']['high']['url'],
                            'published_at': item['snippet']['publishedAt']
                        }
                        videos.append(video)
                    return videos
                else:
                    return []
    except Exception as e:
        return []

async def search_genius_lyrics(query):
    try:
        song = genius.search_song(query)
        if song:
            return {
                'title': song.title,
                'artist': song.artist,
                'url': song.url,
                'lyrics': song.lyrics
            }
        return None
    except Exception as e:
        return None

user_states = {}

@dp.message(Command("start"))
@log_to_csv("Start command", "Telegram", "Bot started")
async def cmd_start(message: types.Message):
    kb = [
        [types.KeyboardButton(text="Поиск треков")],
        [types.KeyboardButton(text="Поиск альбомов")],
        [types.KeyboardButton(text="Поиск на YouTube")],
        [types.KeyboardButton(text="Текст песни")]
    ]
    
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await safe_send_message(
        message.chat.id,
        "Привет! Я музыкальный бот от kagace\nВыбери, что тебе интересно:",
        reply_markup=keyboard
    )

@dp.message(Command("help"))
@log_to_csv("Help command", "Telegram", "Help message")
async def cmd_help(message: types.Message):
    help_text = """
*Музыкальный бот - Помощь*

*Основные команды:*
/start - Запустить бота
/help - Эта справка

*Функции:*
Поиск треков - Ищите музыку в Spotify
Поиск альбомов - Найдите альбомы исполнителей
Поиск на YouTube - Ищите видео на YouTube
Текст песни - Найдите текст песни
"""
    await safe_send_message(message.chat.id, help_text, parse_mode='Markdown')

@dp.message(F.text.lower() == "поиск треков")
@log_to_csv("Track search init", "Telegram", "Waiting for track query")
async def ask_track_search(message: types.Message):
    user_states[message.from_user.id] = "waiting_track_query"
    await safe_send_message(message.chat.id, "Введите название трека для поиска:")

@dp.message(F.text.lower() == "поиск альбомов")
@log_to_csv("Album search init", "Telegram", "Waiting for album query")
async def ask_album_search(message: types.Message):
    user_states[message.from_user.id] = "waiting_album_query"
    await safe_send_message(message.chat.id, "Введите название альбомов для поиска:")

@dp.message(F.text.lower() == "поиск на youtube")
@log_to_csv("YouTube search init", "Telegram", "Waiting for YouTube query")
async def ask_youtube_search(message: types.Message):
    user_states[message.from_user.id] = "waiting_youtube_query"
    await safe_send_message(message.chat.id, "Введите запрос для поиска видео на YouTube:")

@dp.message(F.text.lower() == "текст песни")
@log_to_csv("Lyrics search init", "Telegram", "Waiting for lyrics query")
async def ask_lyrics_search(message: types.Message):
    user_states[message.from_user.id] = "waiting_lyrics_query"
    await safe_send_message(message.chat.id, "Введите название песни и исполнителя:")

@dp.message(F.text)
@log_to_csv("Keyboard typing", "NONE", "NONE")
async def handle_all_text_messages(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    
    if user_id in user_states:
        if user_states[user_id] == "waiting_track_query":
            await safe_send_message(message.chat.id, "Ищу треки...")
            tracks = await search_spotify_tracks(text)
            
            if not tracks:
                await safe_send_message(message.chat.id, "Ничего не найдено")
            else:
                track = tracks[0]
                caption = f"*{escape_markdown(track['artist'])}* - {escape_markdown(track['name'])}\nАльбом: {escape_markdown(track['album'])}\n[Слушать на Spotify]({track['url']})"
                
                if track['image_url']:
                    try:
                        await message.answer_photo(photo=track['image_url'], caption=caption, parse_mode='Markdown')
                    except:
                        await safe_send_message(message.chat.id, caption, parse_mode='Markdown')
                else:
                    await safe_send_message(message.chat.id, caption, parse_mode='Markdown')
            
            del user_states[user_id]
            
        elif user_states[user_id] == "waiting_album_query":
            await safe_send_message(message.chat.id, "Ищу альбомы...")
            albums = await search_spotify_albums(text)
            
            if not albums:
                await safe_send_message(message.chat.id, "Ничего не найдено")
            else:
                album = albums[0]
                caption = f"*{escape_markdown(album['artist'])}* - {escape_markdown(album['name'])}\nДата релиза: {album['release_date']}\n[Слушать на Spotify]({album['url']})"
                
                if album['image_url']:
                    try:
                        await message.answer_photo(photo=album['image_url'], caption=caption, parse_mode='Markdown')
                    except:
                        await safe_send_message(message.chat.id, caption, parse_mode='Markdown')
                else:
                    await safe_send_message(message.chat.id, caption, parse_mode='Markdown')
            
            del user_states[user_id]
            
        elif user_states[user_id] == "waiting_youtube_query":
            await safe_send_message(message.chat.id, "Ищу видео на YouTube...")
            videos = await search_youtube_videos(text, limit=3)
            
            if not videos:
                await safe_send_message(message.chat.id, "Ничего не найдено на YouTube")
            else:
                for video in videos:
                    caption = (f"*{escape_markdown(video['title'])}*\n"
                              f"Канал: {escape_markdown(video['channel'])}\n"
                              f"Опубликовано: {video['published_at'][:10]}\n"
                              f"[Смотреть на YouTube]({video['url']})")
                    
                    try:
                        await message.answer_photo(
                            photo=video['thumbnail'],
                            caption=caption,
                            parse_mode='Markdown'
                        )
                    except:
                        await safe_send_message(message.chat.id, caption, parse_mode='Markdown')
            
            del user_states[user_id]
            
        elif user_states[user_id] == "waiting_lyrics_query":
            await safe_send_message(message.chat.id, "Ищу текст песни...")
            
            genius_data = await search_genius_lyrics(text)
            if genius_data and genius_data.get('lyrics'):
                lyrics = genius_data['lyrics']
                if len(lyrics) > 4000:
                    lyrics = lyrics[:4000] + "...\n\n(текст обрезан из-за ограничения длины)"
                
                response_text = (f"*{escape_markdown(genius_data['artist'])}* - {escape_markdown(genius_data['title'])}*\n\n"
                              f"{lyrics}\n\n"
                              f"[Источник]({genius_data['url']})")
                await safe_send_message(message.chat.id, response_text, parse_mode='Markdown')
            
            del user_states[user_id]

async def main():
    print('Идет запуск бота...')
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())