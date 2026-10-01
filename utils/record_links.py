"""YouTube links and Telegram entities; no requests while rendering profiles."""
from html import unescape
import re
from urllib.parse import parse_qs, urlsplit

from aiogram.types import MessageEntity


def youtube_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        parsed = urlsplit(unescape(value.strip()))
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
            return None
        host = parsed.hostname
        if host in ('youtu.be', 'www.youtu.be'):
            video_id = parsed.path.strip('/')
        elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            if parsed.path == '/watch':
                video_id = parse_qs(parsed.query).get('v', [''])[0]
            elif parsed.path.startswith(('/shorts/', '/live/', '/embed/')):
                video_id = parsed.path.split('/')[2]
            else:
                return None
        else:
            return None
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            return f'https://www.youtube.com/watch?v={video_id}'
    except ValueError:
        pass
    return None


class LinkedText(str):
    def __new__(cls, value, entities=()):
        obj = super().__new__(cls, value)
        obj.entities = list(entities)
        return obj


def status_label(record):
    return {'Verified': 'Подтверждено Demonlist', 'Manual': 'Внесено вручную'}.get(
        record['status'], record['status'],
    )


def link_status(entities, prefix, label, record):
    url = youtube_url(record.get('video_url'))
    if url:
        entities.append(MessageEntity(
            type='text_link', offset=len(prefix.encode('utf-16-le')) // 2,
            length=len(label.encode('utf-16-le')) // 2, url=url,
        ))


def page_entities(entities, start, length):
    result = []
    for entity in entities:
        left = max(start, entity.offset)
        right = min(start + length, entity.offset + entity.length)
        if left < right:
            result.append(entity.model_copy(update={'offset': left - start, 'length': right - left}))
    return result
