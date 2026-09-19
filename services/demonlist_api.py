import asyncio
import logging
from typing import Any, Dict, List

import aiohttp

from database.models import (
    add_record,
    get_player_by_id,
    get_player_records,
    update_record_status,
    upsert_levels,
)

logger = logging.getLogger(__name__)

API_BASE_URL = "https://api.demonlist.org"
LEVELS_ENDPOINT = f"{API_BASE_URL}/level/classic/list"
PLAYER_ENDPOINT = f"{API_BASE_URL}/user/record/list"

# The API's unpaginated response currently stalls after roughly 24 KB. Small
# pages avoid that broken chunked response and put a bound on each request.
PAGE_SIZE = 50
PAGE_WINDOW = 20
MAX_LEVELS = 5_000
REQUEST_ATTEMPTS = 3
REQUEST_TIMEOUT = aiohttp.ClientTimeout(
    total=12,
    connect=5,
    sock_connect=5,
    sock_read=7,
)


class DemonlistAPIError(RuntimeError):
    """Raised when Demonlist data cannot be downloaded or validated."""


def _get_collection(payload: Any, key: str) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        raise DemonlistAPIError("API returned a non-object response")

    data = payload.get("data")
    collection = data.get(key) if isinstance(data, dict) else None
    if not isinstance(collection, list):
        raise DemonlistAPIError(f"API response does not contain data.{key}")
    return collection


async def _request_collection(session, endpoint: str, key: str, params: dict):
    for attempt in range(1, REQUEST_ATTEMPTS + 1):
        try:
            async with session.get(endpoint, params=params) as response:
                response.raise_for_status()
                return _get_collection(await response.json(), key)
        except DemonlistAPIError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            if attempt == REQUEST_ATTEMPTS:
                offset = params.get("offset", 0)
                raise DemonlistAPIError(
                    f"request for {key} at offset {offset} failed after "
                    f"{REQUEST_ATTEMPTS} attempts: {exc}"
                ) from exc
            await asyncio.sleep(0.5 * attempt)


async def _fetch_all_levels(session) -> List[Dict[str, Any]]:
    levels: List[Dict[str, Any]] = []
    seen_ids = set()

    window_size = PAGE_SIZE * PAGE_WINDOW
    for base_offset in range(0, MAX_LEVELS, window_size):
        pages = await asyncio.gather(*(
            _request_collection(
                session,
                LEVELS_ENDPOINT,
                "levels",
                {"limit": PAGE_SIZE, "offset": offset},
            )
            for offset in range(base_offset, base_offset + window_size, PAGE_SIZE)
        ))

        reached_end = False
        for page in pages:
            for level in page:
                level_id = level.get("id") if isinstance(level, dict) else None
                if level_id is None or level_id in seen_ids:
                    continue
                seen_ids.add(level_id)
                levels.append(level)

            if len(page) < PAGE_SIZE:
                reached_end = True
                break

        if reached_end:
            break
    else:
        raise DemonlistAPIError(
            f"level list exceeded the safety limit of {MAX_LEVELS} entries"
        )

    if not levels:
        raise DemonlistAPIError("API returned an empty level list")
    return levels


def _normalize_level(level: Dict[str, Any]):
    level_id = level.get("id")
    level_name = level.get("name")
    position = level.get("placement")
    if level_id is None or not level_name or position is None:
        return None

    creator_obj = (
        level.get("holder")
        or level.get("publisher")
        or level.get("creator")
        or level.get("verifier")
    )
    creator = "Unknown"
    if isinstance(creator_obj, dict):
        creator = creator_obj.get("username") or creator_obj.get("name") or "Unknown"
    elif isinstance(creator_obj, str):
        creator = creator_obj

    ingame_id = level.get("ingame_id")
    if ingame_id is not None:
        ingame_id = int(ingame_id)

    return (
        int(level_id),
        str(level_name),
        int(position),
        creator,
        ingame_id,
    )


async def fetch_levels(progress_callback=None) -> int:
    """Download every level page and atomically update the local cache."""
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            raw_levels = await _fetch_all_levels(session)

        levels = []
        for level in raw_levels:
            normalized = _normalize_level(level)
            if normalized is not None:
                levels.append(normalized)

        if not levels:
            raise DemonlistAPIError("API returned no valid levels")

        if progress_callback:
            await progress_callback(0, len(levels))
        await upsert_levels(levels)
        if progress_callback:
            await progress_callback(len(levels), len(levels))

        logger.info("Successfully updated %s levels in cache.", len(levels))
        return len(levels)
    except DemonlistAPIError:
        logger.exception("Failed to fetch levels from Demonlist API")
        raise
    except Exception as exc:
        logger.exception("Failed to update the level cache")
        raise DemonlistAPIError(f"database update failed: {exc}") from exc


async def sync_player_records(player_id: int) -> bool:
    """Synchronize accepted 100% records for one configured player."""
    player = await get_player_by_id(player_id)
    if not player or not player["api_sync"] or player["demonlist_id"] == "-":
        return True

    demonlist_id = player["demonlist_id"]
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            offset = 0
            verified_level_ids = set()

            while True:
                api_records = await _request_collection(
                    session,
                    PLAYER_ENDPOINT,
                    "records",
                    {
                        "user_id": demonlist_id,
                        "limit": PAGE_SIZE,
                        "offset": offset,
                    },
                )
                if not api_records:
                    break

                for record in api_records:
                    progress = record.get("percent", 100)
                    status = record.get("status", "accepted")
                    if progress == 100 and status == "accepted":
                        level_info = record.get("level", {})
                        if "id" in level_info:
                            verified_level_ids.add(int(level_info["id"]))

                if len(api_records) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE

        local_records = await get_player_records(player_id)
        local_level_ids = set()

        for record in local_records:
            local_level_ids.add(record["level_id"])
            is_manual_completion = (
                record["status"] == "Manual"
                and record["progress_start"] == 0
                and record["progress_end"] == 100
            )
            if is_manual_completion and record["level_id"] in verified_level_ids:
                await update_record_status(record["id"], "Verified")
                logger.info(
                    "Verified record ID %s for player %s",
                    record["id"],
                    player["nickname"],
                )

        for level_id in verified_level_ids:
            if level_id not in local_level_ids:
                await add_record(player_id, level_id, 0, 100, "Verified")
                logger.info(
                    "Auto-added verified level %s for player %s",
                    level_id,
                    player["nickname"],
                )
        return True
    except Exception:
        logger.exception("Error syncing player %s records", player["nickname"])
        return False
