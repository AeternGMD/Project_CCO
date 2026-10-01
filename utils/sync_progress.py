"""Small, plain-text progress indicators for manual record synchronization."""


def progress_bar(current, total):
    fraction = min(1, max(0, current / total)) if total else 1
    filled = int(20 * fraction)
    return f"[{'█' * filled}{'░' * (20 - filled)}] {current}/{total} · {int(fraction * 100)}%"


def record_sync_text(levels, done, players, nickname='', stage='download', current=0, total=None):
    text = f'✅ Обновлено уровней: {levels}\n\nСинхронизация прохождений\n'
    text += f'Обработано игроков: {progress_bar(done, players)}'
    if nickname:
        text += f'\n\nИгрок: {nickname}'
        if stage == 'download':
            text += f'\nЗагружаю записи из Demonlist… Получено: {current}.'
        else:
            text += f'\nОбработка прохождений и ссылок:\n{progress_bar(current, total)}'
    return text
