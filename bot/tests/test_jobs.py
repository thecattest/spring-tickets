"""Обёртка задач и notify_owner — без обращений к VK."""

import pytest

import notify
from jobs import runner


class TestRunJob:
    def test_success_exits_normally(self, monkeypatch):
        sent = []
        monkeypatch.setattr(runner, "notify_owner", lambda text, **kw: _record(sent, text))

        async def ok():
            pass

        runner.run_job("ok", ok())  # не бросает SystemExit
        assert sent == []

    def test_failure_notifies_owner_and_exits_1(self, monkeypatch):
        sent = []
        monkeypatch.setattr(runner, "notify_owner", lambda text, **kw: _record(sent, text))

        async def broken():
            raise RuntimeError("disk full")

        with pytest.raises(SystemExit) as exc:
            runner.run_job("backup", broken())
        assert exc.value.code == 1
        assert sent == ["⚠️ Задача backup упала: RuntimeError: disk full"]


@pytest.mark.asyncio
class TestNotifyOwner:
    async def test_never_raises(self, monkeypatch):
        monkeypatch.setattr(notify.config, "VK_BOT_TOKEN", "vk1.a.fake")
        monkeypatch.setattr(notify.config, "OWNER_VK_IDS", [1])

        def broken_api(token):
            raise RuntimeError("VK is down")

        monkeypatch.setattr(notify, "API", broken_api)
        await notify.notify_owner("hello")  # ошибка только в лог

    async def test_without_config_does_nothing(self, monkeypatch):
        monkeypatch.setattr(notify.config, "OWNER_VK_IDS", [])

        def must_not_be_called(token):
            raise AssertionError("API must not be created")

        monkeypatch.setattr(notify, "API", must_not_be_called)
        await notify.notify_owner("hello")


async def _record(sent: list, text: str) -> None:
    sent.append(text)
