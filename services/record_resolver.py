"""Exact, indexed command resolution; no network calls or fuzzy guesses."""
from dataclasses import dataclass
import re


def key(value):
    return ' '.join(value.split()).casefold()


@dataclass(frozen=True)
class Token:
    text: str
    quoted: bool = False


def tokenize(text):
    tokens = []
    i = 0
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        if text[i] in '\"\'':
            quote = text[i]
            end = text.find(quote, i + 1)
            if end == -1:
                raise ValueError('Незакрытая кавычка. Можно использовать ввод без кавычек.')
            tokens.append(Token(text[i + 1:end], True))
            i = end + 1
        elif text[i] in ',:=|':
            tokens.append(Token(text[i]))
            i += 1
        else:
            end = i + 1
            while end < len(text) and not text[end].isspace() and text[end] not in ',:=|':
                end += 1
            tokens.append(Token(text[i:end]))
            i = end
    return tokens


def separator(token, char):
    return not token.quoted and token.text == char


def joined(tokens):
    return ' '.join(token.text for token in tokens).strip()


@dataclass(frozen=True)
class RecordOption:
    level_id: int
    name: str
    creator: str
    progresses: tuple
    position: int | None = None

    @property
    def label(self):
        progress = ' | '.join(f'{start}-{end}%' if start else f'{end}%'
                              for start, end in self.progresses)
        place = f'Топ-{self.position} · ' if self.position is not None else ''
        return f'{place}{progress} — {self.name} [{self.creator}]'


@dataclass
class RecordPlan:
    player_id: int
    nickname: str
    groups: list


class RecordCatalog:
    def __init__(self, players, levels):
        self.players_by_id = {p['id']: p for p in players}
        self.players_by_name = {}
        self.levels_by_id = {l['level_id']: l for l in levels}
        self.levels_by_name = {}
        for player in players:
            self.players_by_name.setdefault(key(player['nickname']), []).append(player)
        for level in levels:
            self.levels_by_name.setdefault(key(level['level_name']), []).append(level)

    def players(self, text):
        if re.fullmatch(r'@\d+', text):
            player = self.players_by_id.get(int(text[1:]))
            return [player] if player else []
        return self.players_by_name.get(key(text), [])

    def levels(self, tokens):
        text = joined(tokens)
        # Numbers are names, never IDs. Internal IDs are only used after
        # resolving a name (or selecting a disambiguation button).
        return list(self.levels_by_name.get(key(text), []))


def progresses(tokens):
    text = joined(tokens)
    if not re.fullmatch(r'\d+(?:-\d+)?%?(?:\s*\|\s*\d+(?:-\d+)?%?)*', text):
        raise ValueError('Прогресс: 60%, 40-100 или 60 | 40-100.')
    result = []
    for part in text.split('|'):
        values = part.strip().rstrip('%').split('-')
        start, end = (0, int(values[0])) if len(values) == 1 else map(int, values)
        if not 0 <= start < end <= 100:
            raise ValueError('Прогресс должен быть в пределах 0–100%.')
        if end < 100 and end - start < 40:
            raise ValueError('Прогресс должен покрывать минимум 40% уровня.')
        if (start, end) not in result:
            result.append((start, end))
    return tuple(result)


def level_options(tokens, catalog, action):
    options = []

    def append(level_tokens, runs):
        for level in catalog.levels(level_tokens):
            option = RecordOption(level['level_id'], level['level_name'],
                                  level.get('creator') or 'Автор не указан', runs,
                                  level.get('position'))
            if option not in options:
                options.append(option)

    equals = [i for i, token in enumerate(tokens) if separator(token, '=')]
    if equals:
        if action == 'del' or len(equals) != 1:
            raise ValueError('Для удаления укажите только название уровня.')
        i = equals[0]
        append(tokens[:i], progresses(tokens[i + 1:]))
    else:
        append(tokens, ((0, 100),))
        if action == 'add':
            for i in range(1, len(tokens)):
                if any(t.quoted for t in tokens[i:]):
                    continue
                try:
                    runs = progresses(tokens[i:])
                except ValueError:
                    continue
                append(tokens[:i], runs)
    if len(options) > 20:
        raise ValueError('Слишком много совпадений. Уточните полное название уровня; если оно повторяется, обратитесь к администратору.')
    return options


def resolve_record_command(text, catalog, action='add'):
    if len(text) > 4096:
        raise ValueError('Команда слишком длинная.')
    body = text.split(maxsplit=1)
    if len(body) < 2:
        raise ValueError('Укажите ник и названия уровней через запятую.')
    tokens = tokenize(body[1])
    colon = next((i for i, t in enumerate(tokens) if separator(t, ':')), None)
    candidates = []
    boundaries = [colon] if colon is not None else range(1, len(tokens))
    for i in boundaries:
        prefix = tokens[:i]
        if any(not t.quoted and t.text in ',=|' for t in prefix):
            break
        name = joined(prefix)
        if len(name) > 255:
            break
        for player in catalog.players(name):
            rest = tokens[i + 1:] if colon is not None else tokens[i:]
            candidates.append((player, rest))

    plans = []
    missing = set()
    for player, rest in candidates:
        groups = [[]]
        for token in rest:
            if separator(token, ','):
                groups.append([])
            else:
                groups[-1].append(token)
        if any(not joined(group) for group in groups):
            raise ValueError('Между запятыми и после них должно быть название уровня.')
        if len(groups) > 100:
            raise ValueError('За одну команду можно указать до 100 уровней.')
        resolved = []
        for group in groups:
            options = level_options(group, catalog, action)
            if not options:
                missing.add(joined(group))
            resolved.append(options)
        if all(resolved):
            plans.append(RecordPlan(player['id'], player['nickname'], resolved))
    if not plans:
        if missing:
            names = ', '.join(sorted(missing))[:700]
            hint = ' Проценты указывайте после =, например: = 60%.' if action == 'add' else ''
            raise ValueError(f'Проверьте названия уровней: {names}. '
                             'Используйте названия, не ID Demonlist. Ничего не изменено.' + hint)
        raise ValueError('Игрок не найден. Отделите ник двоеточием: ник: название уровня.')
    if len(plans) > 20:
        raise ValueError('Слишком много вариантов. Уточните игрока через «ник:» или @ID.')
    if sum(len(group) for plan in plans for group in plan.groups) > 200:
        raise ValueError('Слишком много совпадений. Разделите список на несколько команд и укажите полные названия.')
    return plans
