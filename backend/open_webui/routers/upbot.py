"""
Reverse-proxy router for upbot.

upbot exposes a bespoke {message, session_id, user_id} / SSE contract, not
an OpenAI-compatible API, so this translates in both directions instead of
being a thin passthrough like routers/ollama.py or routers/openai.py.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import time
import uuid

import aiohttp
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from open_webui.config import UPBOT_API_KEYS, UPBOT_BASE_URL, UPBOT_USER_ID, WEBUI_URL, ENABLE_UPBOT_API
from open_webui.env import AIOHTTP_CLIENT_SESSION_SSL
from open_webui.models.chats import Chats
from open_webui.models.files import FileForm, Files
from open_webui.models.models import ModelForm, Models
from open_webui.models.users import UserModel
from open_webui.storage.provider import Storage
from open_webui.utils.json_codec import JSONCodec
from open_webui.utils.misc import (
    openai_chat_chunk_message_template,
    openai_chat_completion_message_template,
)
from open_webui.utils.session_pool import cleanup_response, get_client_timeout, get_session

log = logging.getLogger(__name__)

router = APIRouter()

MODEL_ID_PREFIX = 'upbot-'
# Separates the channel from an explicit upbot model id:
#   upbot-chat              -> channel 'chat', no explicit model (upbot picks its default)
#   upbot-chat:qwen3.6-35b  -> channel 'chat', model 'qwen3.6-35b'
MODEL_ID_SEP = ':'


def parse_model_id(model_id: str) -> tuple[str, str | None]:
    rest = model_id[len(MODEL_ID_PREFIX):] if model_id.startswith(MODEL_ID_PREFIX) else model_id
    channel, sep, model = rest.partition(MODEL_ID_SEP)
    return channel, (model if sep else None)


def channel_to_model_id(channel: str) -> str:
    return f'{MODEL_ID_PREFIX}{channel}'


@router.get('/')
@router.head('/')
async def get_status() -> dict:
    return {'status': bool(ENABLE_UPBOT_API and UPBOT_BASE_URL)}


# Shown when upbot's /channels/me is unreachable or times out.
_FALLBACK_DESCRIPTION = (
    '¡Hola! Soy UPB AI Agent. Puedo ayudarte con: '
    '📚 info institucional, 📊 consultas de datos, 📄 reportes en PDF y Excel.'
)
_CHANNEL_INFO_TTL_SECONDS = 300
_CHANNEL_INFO_TIMEOUT = aiohttp.ClientTimeout(total=3)
_channel_info_cache: dict[str, tuple[float, str]] = {}
# channel -> (fetched_at, [model ids from upbot's GET /models]). Empty list on
# any failure, so the model list never blocks on upbot being reachable.
_channel_models_cache: dict[str, tuple[float, list[str]]] = {}


async def _sync_description_to_model_row(model_id: str, description: str) -> None:
    """
    If a model row already exists (created e.g. by granting a user access),
    keep its stored description in sync with upbot's live value - otherwise
    that row freezes the description forever at whatever it was when created.
    Only touches `meta.description`; access grants and any other admin
    customization on the row are left untouched.
    """
    try:
        model = await Models.get_model_by_id(model_id)
        if model is None or model.meta.description == description:
            return
        form = ModelForm(
            id=model_id,
            base_model_id=model.base_model_id,
            name=model.name,
            meta=model.meta.model_copy(update={'description': description}),
            params=model.params,
            access_grants=None,
            is_active=model.is_active,
        )
        await Models.update_model_by_id(model_id, form)
    except Exception as e:
        log.warning('upbot: failed to sync description to model row "%s": %s', model_id, e)


async def _fetch_channel_description(channel: str, api_key: str) -> tuple[str, bool]:
    """
    Returns (description, fetched). `fetched` is True only when upbot returned a
    real description this call - False for a cache hit or the fallback, so
    callers know whether the value is safe to write back to a model row.
    """
    cached = _channel_info_cache.get(channel)
    now = time.monotonic()
    if cached and now - cached[0] < _CHANNEL_INFO_TTL_SECONDS:
        return cached[1], False

    description = _FALLBACK_DESCRIPTION
    fetched = False
    try:
        session = await get_session()
        r = await session.get(
            f'{UPBOT_BASE_URL}/channels/me',
            headers={'X-Api-Key': api_key},
            ssl=AIOHTTP_CLIENT_SESSION_SSL,
            timeout=_CHANNEL_INFO_TIMEOUT,
        )
        try:
            if r.ok:
                data = await r.json(loads=JSONCodec.loads)
                if data.get('description'):
                    description = data['description']
                    fetched = True
        finally:
            await cleanup_response(r)
    except Exception as e:
        log.warning('upbot: failed to fetch /channels/me for channel "%s": %s', channel, e)

    _channel_info_cache[channel] = (now, description)
    return description, fetched


async def _fetch_channel_models(channel: str, api_key: str) -> list[str]:
    """
    upbot model ids selectable on this channel right now, from GET /models.
    Empty list on any failure - callers fall back to the channel's bare model
    entry (upbot resolves its own default) rather than an empty dropdown.
    """
    cached = _channel_models_cache.get(channel)
    now = time.monotonic()
    if cached and now - cached[0] < _CHANNEL_INFO_TTL_SECONDS:
        return cached[1]

    models: list[str] = []
    try:
        session = await get_session()
        r = await session.get(
            f'{UPBOT_BASE_URL}/models',
            headers={'X-Api-Key': api_key},
            ssl=AIOHTTP_CLIENT_SESSION_SSL,
            timeout=_CHANNEL_INFO_TIMEOUT,
        )
        try:
            if r.ok:
                data = await r.json(loads=JSONCodec.loads)
                models = [m for m in data.get('models', []) if isinstance(m, str)]
        finally:
            await cleanup_response(r)
    except Exception as e:
        log.warning('upbot: failed to fetch /models for channel "%s": %s', channel, e)

    _channel_models_cache[channel] = (now, models)
    return models


def _model_entry(model_id: str, name: str, channel: str, description: str) -> dict:
    return {
        'id': model_id,
        'name': name,
        'object': 'model',
        'created': 0,
        'owned_by': 'upbot',
        'upbot': {'channel': channel},
        'info': {
            'meta': {
                'description': description,
                # upbot's tools are RAG search, warehouse SQL, and PDF/Excel
                # generation only - none are vision/web-search/image-gen/code-exec,
                # so these stay False regardless of channel or model.
                'capabilities': {
                    'vision': False,
                    'file_upload': False,
                    'web_search': False,
                    'image_generation': False,
                    'code_interpreter': False,
                    'terminal': False,
                },
            },
        },
    }


async def get_all_models(request: Request, user: UserModel = None) -> list[dict]:
    """
    Per configured upbot channel: a bare `upbot-<channel>` entry (upbot picks
    its own default model) plus one `upbot-<channel>:<model>` entry per model
    upbot currently reports as selectable. Each model keeps its own upbot
    session, so side-by-side compare branches stay isolated.
    """
    if not (ENABLE_UPBOT_API and UPBOT_BASE_URL):
        return []

    per_channel = await asyncio.gather(
        *(
            asyncio.gather(
                _fetch_channel_description(channel, api_key),
                _fetch_channel_models(channel, api_key),
            )
            for channel, api_key in UPBOT_API_KEYS.items()
        )
    )

    models: list[dict] = []
    sync_tasks = []
    for channel, ((description, fetched), model_ids) in zip(UPBOT_API_KEYS, per_channel):
        bare = channel_to_model_id(channel)
        ids = [bare, *(f'{bare}{MODEL_ID_SEP}{m}' for m in model_ids)]
        names = ['UPB AI Agent', *(f'UPB AI Agent ({m})' for m in model_ids)]
        models += [_model_entry(i, n, channel, description) for i, n in zip(ids, names)]
        # Keep any existing model rows' stored description in sync with upbot's
        # live value, but never write back the fallback (see the outage note in
        # _fetch_channel_description). Runs here, where both fetches have
        # resolved, so every per-model id is covered.
        if fetched:
            sync_tasks += [_sync_description_to_model_row(i, description) for i in ids]

    if sync_tasks:
        await asyncio.gather(*sync_tasks)
    return models


def _extract_last_user_message(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get('role') != 'user':
            continue
        content = message.get('content')
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return ''.join(part.get('text', '') for part in content if part.get('type') == 'text')
    return ''


async def convert_payload_openai_to_upbot(form_data: dict, chat_id: str | None, model_id: str) -> dict:
    payload = {'message': _extract_last_user_message(form_data.get('messages', []))}

    _, model = parse_model_id(model_id)
    if model:
        payload['model'] = model

    session_id = await Chats.get_upbot_session_id(chat_id, model_id) if chat_id else None
    if session_id:
        payload['session_id'] = session_id

    if UPBOT_USER_ID:
        payload['user_id'] = UPBOT_USER_ID

    return payload


def convert_response_upbot_to_openai(model_id: str, upbot_response: dict) -> dict:
    # upbot's non-streaming /chat never returns generated PDF/Excel files,
    # only /chat/stream does - nothing to carry over here even if a tool ran.
    return openai_chat_completion_message_template(model_id, upbot_response.get('reply', ''))


async def _store_upbot_file(file_event: dict, user: UserModel, base_url: str) -> str:
    """
    Persist a base64 file from upbot's SSE `file` event and return a markdown link to it.
    """
    filename = file_event.get('filename', 'file')
    mime = file_event.get('mime', '')
    raw = base64.b64decode(file_event.get('data', ''))

    file_id = str(uuid.uuid4())
    tags = {
        'OpenWebUI-User-Id': user.id,
        'OpenWebUI-File-Id': file_id,
    }
    contents, file_path = await asyncio.to_thread(
        Storage.upload_file, io.BytesIO(raw), f'{file_id}_{filename}', tags
    )

    file_item = await Files.insert_new_file(
        user.id,
        FileForm(
            id=file_id,
            filename=filename,
            path=file_path,
            meta={
                'name': filename,
                'content_type': mime or None,
                'size': len(contents),
                'file_hash': hashlib.sha256(contents).hexdigest(),
            },
        ),
    )
    if file_item is None:
        # insert_new_file() swallows its own exceptions and returns None on
        # failure instead of raising - check explicitly so a silent DB error
        # doesn't produce a link to a file that was never actually saved.
        raise RuntimeError(f'Files.insert_new_file() returned None for "{filename}"')

    icon = '📄' if 'pdf' in mime else '📊'
    return f'\n\n[{icon} {filename}]({base_url}/api/v1/files/{file_id}/content)'


async def convert_streaming_response_upbot_to_openai(
    response: aiohttp.ClientResponse, model_id: str, chat_id: str | None, user: UserModel, base_url: str
):
    completion_id = f'chatcmpl-{uuid.uuid4()}'
    buffer = ''
    try:
        async for chunk_bytes in response.content.iter_any():
            buffer += chunk_bytes.decode('utf-8', errors='ignore')
            *lines, buffer = buffer.split('\n\n')

            for line in lines:
                line = line.strip()
                if not line.startswith('data:'):
                    continue
                try:
                    event = JSONCodec.loads(line[len('data:'):].strip())
                except ValueError:
                    continue

                if 'chunk' in event:
                    data = openai_chat_chunk_message_template(model_id, event['chunk'], message_id=completion_id)
                    yield f'data: {JSONCodec.dumps(data)}\n\n'

                elif event.get('thinking'):
                    # No tool name in the wire contract - nothing to surface yet.
                    pass

                elif 'file' in event:
                    try:
                        link = await _store_upbot_file(event['file'], user, base_url)
                    except Exception:
                        log.exception('upbot: failed to store file attachment "%s"', event['file'].get('filename', '?'))
                        continue
                    data = openai_chat_chunk_message_template(model_id, link, message_id=completion_id)
                    yield f'data: {JSONCodec.dumps(data)}\n\n'

                elif 'error' in event:
                    data = openai_chat_chunk_message_template(
                        model_id, f'\n\n[upbot error: {event["error"]}]', message_id=completion_id
                    )
                    yield f'data: {JSONCodec.dumps(data)}\n\n'

                elif event.get('done'):
                    if chat_id and event.get('session_id'):
                        await Chats.set_upbot_session_id(chat_id, model_id, event['session_id'])
                    data = openai_chat_chunk_message_template(model_id, None, message_id=completion_id)
                    data['choices'][0]['delta'] = {}
                    data['choices'][0]['finish_reason'] = 'stop'
                    yield f'data: {JSONCodec.dumps(data)}\n\n'
    finally:
        await cleanup_response(response)

    yield 'data: [DONE]\n\n'


async def generate_chat_completion(request: Request, form_data: dict, user: UserModel):
    if not (ENABLE_UPBOT_API and UPBOT_BASE_URL):
        raise HTTPException(status_code=400, detail='upbot is not configured')

    model_id = form_data.get('model', '')
    channel, _ = parse_model_id(model_id)
    api_key = UPBOT_API_KEYS.get(channel)
    if not api_key:
        raise HTTPException(status_code=400, detail=f'No upbot API key configured for channel "{channel}"')

    metadata = form_data.get('metadata', {}) or {}
    if metadata.get('task'):
        # Title/tags/follow-up generation: upbot has no cheap completion mode,
        # every call is a real agent-loop turn with tools armed. Let
        # open-webui fall back to its default behavior for these instead.
        raise HTTPException(status_code=400, detail='upbot does not support background task generation')

    chat_id = metadata.get('chat_id')
    stream = bool(form_data.get('stream'))

    payload = await convert_payload_openai_to_upbot(form_data, chat_id, model_id)
    path = '/chat/stream' if stream else '/chat'

    headers = {
        'Content-Type': 'application/json',
        'X-Api-Key': api_key,
    }
    if stream:
        headers['Accept'] = 'text/event-stream'

    session = await get_session()
    r = None
    streaming = False
    try:
        r = await session.post(
            f'{UPBOT_BASE_URL}{path}',
            data=JSONCodec.dumps(payload),
            headers=headers,
            ssl=AIOHTTP_CLIENT_SESSION_SSL,
            timeout=get_client_timeout(stream=stream),
        )

        if not r.ok:
            detail = await r.text()
            raise HTTPException(status_code=r.status, detail=f'upbot: {detail}')

        if stream:
            streaming = True
            # WEBUI_URL is the deployment's declared external origin - stable
            # across restarts/host changes, unlike a per-request base_url,
            # which would otherwise get baked permanently into saved messages.
            base_url = WEBUI_URL.rstrip('/') if WEBUI_URL else str(request.base_url).rstrip('/')
            return StreamingResponse(
                convert_streaming_response_upbot_to_openai(r, model_id, chat_id, user, base_url),
                media_type='text/event-stream',
            )

        data = await r.json(loads=JSONCodec.loads)
        if chat_id and data.get('session_id'):
            await Chats.set_upbot_session_id(chat_id, model_id, data['session_id'])
        return convert_response_upbot_to_openai(model_id, data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'upbot: {e}')
    finally:
        # streaming only flips True once ownership of `r` has actually
        # transferred to the generator's own cleanup - stays False (so this
        # cleans up here) on any exception raised before that handoff,
        # including a non-ok response on a streaming request.
        if not streaming:
            await cleanup_response(r)
