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
import uuid

import aiohttp
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from open_webui.config import UPBOT_API_KEYS, UPBOT_BASE_URL, UPBOT_USER_ID, WEBUI_URL, ENABLE_UPBOT_API
from open_webui.env import AIOHTTP_CLIENT_SESSION_SSL
from open_webui.models.chats import Chats
from open_webui.models.files import FileForm, Files
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


def model_id_to_channel(model_id: str) -> str:
    return model_id[len(MODEL_ID_PREFIX):] if model_id.startswith(MODEL_ID_PREFIX) else model_id


def channel_to_model_id(channel: str) -> str:
    return f'{MODEL_ID_PREFIX}{channel}'


@router.get('/')
@router.head('/')
async def get_status() -> dict:
    return {'status': bool(ENABLE_UPBOT_API and UPBOT_BASE_URL)}


async def get_all_models(request: Request, user: UserModel = None) -> list[dict]:
    """
    One synthetic model per configured upbot channel/API key.
    """
    if not (ENABLE_UPBOT_API and UPBOT_BASE_URL):
        return []
    return [
        {
            'id': channel_to_model_id(channel),
            'name': f'upbot ({channel})',
            'object': 'model',
            'created': 0,
            'owned_by': 'upbot',
            'upbot': {'channel': channel},
        }
        for channel in UPBOT_API_KEYS
    ]


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


async def convert_payload_openai_to_upbot(form_data: dict, chat_id: str | None) -> dict:
    payload = {'message': _extract_last_user_message(form_data.get('messages', []))}

    session_id = await Chats.get_upbot_session_id(chat_id) if chat_id else None
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
                        await Chats.set_upbot_session_id(chat_id, event['session_id'])
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
    channel = model_id_to_channel(model_id)
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

    payload = await convert_payload_openai_to_upbot(form_data, chat_id)
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
            await Chats.set_upbot_session_id(chat_id, data['session_id'])
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
