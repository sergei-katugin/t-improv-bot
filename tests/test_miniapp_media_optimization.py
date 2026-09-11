from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import miniapp_media
import miniapp_promotion
from tests.miniapp_support import _Request, web


def test_announcement_audience_selects_the_requested_description():
    show = SimpleNamespace(poster_text="Для своих", poster_text_newcomer="Для новичков")

    assert miniapp_promotion._announcement_show(show, "familiar").poster_text == "Для своих"
    assert miniapp_promotion._announcement_show(show, "newcomer").poster_text == "Для новичков"
    assert show.poster_text == "Для своих"


def _fake_pillow(monkeypatch, *, image_format="PNG"):
    opened = []

    class ImageObject:
        format = image_format
        width, height = 2400, 1200
        mode = "RGBA"
        size = (1600, 800)

        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def verify(self): pass
        def thumbnail(self, size, resample): self.thumbnail_args = (size, resample)
        def getchannel(self, channel): return f"channel:{channel}"
        def save(self, output, **kwargs): output.write(b"optimized-jpeg")

    class Background(ImageObject):
        mode = "RGB"
        def paste(self, image, mask): self.paste_args = (image, mask)

    class ImageApi:
        DecompressionBombError = RuntimeError
        Resampling = SimpleNamespace(LANCZOS="lanczos")

        @staticmethod
        def open(_stream):
            image = ImageObject(); opened.append(image); return image

        @staticmethod
        def new(mode, size, color):
            background = Background(); background.new_args = (mode, size, color); return background

    pillow = SimpleNamespace(
        Image=ImageApi,
        ImageOps=SimpleNamespace(exif_transpose=lambda image: image),
        UnidentifiedImageError=ValueError,
    )
    monkeypatch.setitem(__import__("sys").modules, "PIL", pillow)
    return opened


def test_poster_is_resized_flattened_and_saved_as_optimized_jpeg(monkeypatch):
    opened = _fake_pillow(monkeypatch)

    assert miniapp_media._optimized_poster_bytes(b"original") == b"optimized-jpeg"
    assert opened[1].thumbnail_args == ((1600, 1600), "lanczos")


def test_poster_optimizer_rejects_unsupported_image_content(monkeypatch):
    _fake_pillow(monkeypatch, image_format="GIF")

    with pytest.raises(miniapp_media.InvalidPosterError):
        miniapp_media._optimized_poster_bytes(b"gif")


@pytest.mark.asyncio
async def test_long_test_announcement_sends_photo_then_text():
    bot = AsyncMock()
    show = SimpleNamespace(poster_file_id="poster-id")
    keyboard = object()

    await miniapp_promotion._send_test_announcement_message(
        bot, 42, show, "x" * 1025, keyboard,
    )

    bot.send_photo.assert_awaited_once_with(42, "poster-id")
    bot.send_message.assert_awaited_once_with(42, "x" * 1025, reply_markup=keyboard)


@pytest.mark.asyncio
async def test_test_announcement_without_poster_sends_one_text_message():
    bot = AsyncMock()
    show = SimpleNamespace(poster_file_id=None)
    keyboard = object()

    await miniapp_promotion._send_test_announcement_message(bot, 42, show, "Анонс", keyboard)

    bot.send_photo.assert_not_awaited()
    bot.send_message.assert_awaited_once_with(42, "Анонс", reply_markup=keyboard)


@pytest.mark.asyncio
@pytest.mark.parametrize("body,error", [
    ({"unexpected": True}, "invalid_payload"),
    ({"repeat": True}, "confirmation_required"),
    ({"repeat": True, "confirmed": True, "idempotencyKey": "short"}, "invalid_idempotency_key"),
])
async def test_publish_rejects_invalid_repeat_requests_before_database_access(body, error):
    request = _Request(show_id=7, user_id=1, body=body)

    with pytest.raises(web.HTTPBadRequest) as caught:
        await miniapp_promotion.miniapp_publish(request)

    assert error in caught.value.text
