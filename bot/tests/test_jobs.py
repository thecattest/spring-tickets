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
        monkeypatch.setattr(notify, "vk_settings", lambda: _vk(owner_vk_ids=[1]))

        def broken_api(token):
            raise RuntimeError("VK is down")

        monkeypatch.setattr(notify, "API", broken_api)
        await notify.notify_owner("hello")  # ошибка только в лог

    async def test_without_config_does_nothing(self, monkeypatch):
        monkeypatch.setattr(notify, "vk_settings", lambda: _vk(owner_vk_ids=[]))

        def must_not_be_called(token):
            raise AssertionError("API must not be created")

        monkeypatch.setattr(notify, "API", must_not_be_called)
        await notify.notify_owner("hello")


async def _record(sent: list, text: str) -> None:
    sent.append(text)


class TestBackup:
    def test_rotate_keeps_newest_per_reason(self, tmp_path):
        from jobs.backup import rotate

        names = [f"tickets-regular-2026111{d}-040000Z.dump" for d in range(5)]
        names += ["tickets-pre-migrate-20261101-120000Z.dump", "unrelated.txt"]
        for name in names:
            (tmp_path / name).touch()

        removed = rotate(tmp_path, "regular", keep=3)

        assert [p.name for p in removed] == names[:2]  # два самых старых
        left = sorted(p.name for p in tmp_path.iterdir())
        assert left == sorted(names[2:])  # предмиграционный и чужой файл не тронуты

    def test_pending_migrations(self):
        from alembic import command

        import database
        from jobs.backup import has_pending_migrations

        assert not has_pending_migrations()  # тестовая база на head
        cfg = database.alembic_config()
        command.downgrade(cfg, "base")
        try:
            assert has_pending_migrations()
        finally:
            command.upgrade(cfg, "head")


@pytest.mark.asyncio
class TestDebtors:
    """Логика рассылки: VK и БД подменены."""

    @pytest.fixture
    def env(self, monkeypatch):
        from types import SimpleNamespace

        from jobs import debtors

        sellers = [SimpleNamespace(id=i, vk_user_id=100 + i) for i in (1, 2, 3)]
        state = {"sent": [], "audited": [], "fail_for": set()}

        class FakeMessages:
            async def send(self, peer_id, message, random_id):
                if peer_id in state["fail_for"]:
                    raise RuntimeError("VK error")
                assert random_id > 0  # не 0: иначе VK не отбрасывает дубли
                state["sent"].append(peer_id)

        class FakeAPI:
            def __init__(self, token):
                self.messages = FakeMessages()
                self.http_client = SimpleNamespace(close=_noop)

        monkeypatch.setattr(debtors, "vk_settings", lambda: _vk(owner_vk_ids=[]))
        monkeypatch.setattr(debtors, "API", FakeAPI)
        monkeypatch.setattr(debtors, "get_all_active_sellers", lambda: sellers)
        # У билетёра 2 должников нет
        monkeypatch.setattr(
            debtors, "get_debtors", lambda seller_id, min_days: [] if seller_id == 2 else [{}]
        )
        monkeypatch.setattr(debtors, "format_reminder", lambda d: "text")
        monkeypatch.setattr(
            debtors,
            "log_reminder_sent",
            lambda seller_id, debtor_count: state["audited"].append(seller_id),
        )
        return debtors, state

    async def test_sends_only_to_sellers_with_debtors(self, env):
        debtors, state = env
        await debtors.send_reminders()
        assert state["sent"] == [101, 103]
        assert state["audited"] == [1, 3]

    async def test_one_failure_does_not_stop_others_but_fails_job(self, env):
        debtors, state = env
        state["fail_for"] = {101}
        with pytest.raises(RuntimeError, match=r"sellers \[1\]"):
            await debtors.send_reminders()
        assert state["sent"] == [103]  # остальным отправлено
        assert state["audited"] == [3]  # аудит только для отправленных


async def _noop():
    pass


def _vk(**overrides):
    from config import VkSettings

    return VkSettings(**{"vk_bot_token": "vk1.a.fake", "vk_group_id": 1, **overrides})


@pytest.mark.asyncio
class TestNotifyDedup:
    async def test_same_key_sent_once_within_interval(self, monkeypatch):
        sent = []
        monkeypatch.setattr(notify, "vk_settings", lambda: _vk(owner_vk_ids=[1]))
        monkeypatch.setattr(notify, "_last_sent", {})

        async def fake_send_all(vk, text, file):
            sent.append(text)

        monkeypatch.setattr(notify, "_send_all", fake_send_all)

        await notify.notify_owner("boom", dedup_key="k")
        await notify.notify_owner("boom", dedup_key="k")  # повтор — не отправляется
        await notify.notify_owner("other", dedup_key="k2")
        await notify.notify_owner("no key")
        await notify.notify_owner("no key")  # без ключа — без ограничения
        assert sent == ["boom", "other", "no key", "no key"]

        # Прошёл интервал — снова отправляется
        notify._last_sent["k"] -= notify.DEDUP_INTERVAL + 1
        await notify.notify_owner("boom", dedup_key="k")
        assert sent[-1] == "boom"


@pytest.mark.asyncio
class TestHeartbeat:
    async def test_touched_after_vk_response(self, monkeypatch, tmp_path):
        from vkbottle import API, BotPolling

        from bot import main

        heartbeat = tmp_path / "hb"
        monkeypatch.setattr(main, "HEARTBEAT_FILE", heartbeat)

        async def fake_get_event(self, server):
            return {"ts": "1", "updates": []}

        monkeypatch.setattr(BotPolling, "get_event", fake_get_event)
        polling = main.HeartbeatPolling(API("vk1.a.fake"))

        assert not heartbeat.exists()
        await polling.get_event({"server": "x"})
        assert heartbeat.exists()

    async def test_not_touched_on_network_error(self, monkeypatch, tmp_path):
        from vkbottle import API, BotPolling

        from bot import main

        heartbeat = tmp_path / "hb"
        monkeypatch.setattr(main, "HEARTBEAT_FILE", heartbeat)

        async def broken_get_event(self, server):
            raise TimeoutError

        monkeypatch.setattr(BotPolling, "get_event", broken_get_event)
        with pytest.raises(TimeoutError):
            await main.HeartbeatPolling(API("vk1.a.fake")).get_event({"server": "x"})
        assert not heartbeat.exists()
