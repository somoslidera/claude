from datetime import datetime

import pytest

from instagram_bot.config import Config, load_config
from instagram_bot.instagram import ActionBlockedError, InstagramError, Profile
from instagram_bot.limits import within_active_hours
from instagram_bot.routine import Routine
from instagram_bot.storage import Storage


class FakeIG:
    def __init__(self, followers, profiles=None, fail_follow=None):
        self.followers = followers
        self.profiles = profiles or {}
        self.fail_follow = fail_follow
        self.calls = []

    def recent_followers(self, me, count):
        return self.followers[:count]

    def get_profile(self, username):
        return self.profiles.get(username) or Profile(
            username, "1", False, False, False, True, ["a", "b", "c"])

    def like_post(self, code):
        self.calls.append(("like", code)); return True

    def follow(self, username):
        if self.fail_follow:
            raise self.fail_follow
        self.calls.append(("follow", username)); return True

    def like_story(self, username):
        self.calls.append(("story_like", username)); return True

    def send_dm(self, username, text):
        self.calls.append(("dm", username, text))


@pytest.fixture
def cfg(tmp_path):
    c = Config(username="me", data_dir=tmp_path, active_hours=(0, 24))
    c.limits.profiles_per_run = 100
    return c


def make(cfg, ig):
    return Routine(cfg, ig, Storage(cfg.db_path), pause=lambda b: None)


def test_first_run_is_baseline_only(cfg):
    ig = FakeIG(["ana", "bia"])
    make(cfg, ig).run()
    assert ig.calls == []


def test_new_follower_full_routine_in_order(cfg):
    ig = FakeIG(["ana"])
    r = make(cfg, ig)
    r.run()                      # baseline
    ig.followers = ["joao", "ana"]  # joão seguiu depois
    r.run()
    assert ig.calls == [("like", "a"), ("like", "b"), ("follow", "joao"), ("story_like", "joao")]
    r.run()                      # não repete
    assert len(ig.calls) == 4


def test_daily_limits_respected(cfg):
    cfg.baseline_on_first_run = False
    cfg.limits.likes_per_day = 3
    cfg.limits.follows_per_day = 1
    ig = FakeIG(["a1", "a2"])
    make(cfg, ig).run()
    assert sum(c[0] == "like" for c in ig.calls) == 3
    assert sum(c[0] == "follow" for c in ig.calls) == 1


def test_dry_run_does_nothing(cfg):
    cfg.baseline_on_first_run = False
    cfg.dry_run = True
    ig = FakeIG(["a1"])
    r = make(cfg, ig)
    r.run()
    assert ig.calls == []
    assert r.storage.count_today("like") == 0  # dry-run não consome limite


def test_private_profile_only_followed(cfg):
    cfg.baseline_on_first_run = False
    ig = FakeIG(["priv"], {"priv": Profile("priv", "2", True, False, False, True, ["x"])})
    make(cfg, ig).run()
    assert ig.calls == [("follow", "priv")]


def test_already_following_not_followed_again(cfg):
    cfg.baseline_on_first_run = False
    ig = FakeIG(["f"], {"f": Profile("f", "3", False, True, False, True, [])})
    make(cfg, ig).run()
    assert ("follow", "f") not in ig.calls


def test_block_stops_run_and_keeps_queue(cfg):
    cfg.baseline_on_first_run = False
    cfg.routine.like_posts = cfg.routine.like_story = False
    ig = FakeIG(["a1", "a2"], fail_follow=ActionBlockedError("bloqueado"))
    r = make(cfg, ig)
    r.run()
    assert set(r.storage.pending_followers(10)) == {"a1", "a2"}


def test_error_on_one_profile_continues(cfg):
    cfg.baseline_on_first_run = False
    cfg.routine.like_posts = cfg.routine.like_story = False
    ig = FakeIG(["a1"], fail_follow=InstagramError("botão não achado"))
    r = make(cfg, ig)
    r.run()
    assert r.storage.pending_followers(10) == []


def test_dm_uses_template(cfg):
    cfg.baseline_on_first_run = False
    cfg.routine.send_dm = True
    cfg.routine.dm_templates = ["Oi {username}!"]
    ig = FakeIG(["zé"])
    make(cfg, ig).run()
    assert ("dm", "zé", "Oi zé!") in ig.calls


def test_active_hours():
    assert within_active_hours((9, 22), datetime(2026, 1, 1, 10))
    assert not within_active_hours((9, 22), datetime(2026, 1, 1, 23))
    assert within_active_hours((22, 2), datetime(2026, 1, 1, 1))


def test_example_config_loads():
    c = load_config("config.example.yaml")
    assert c.delays.between_actions == (4, 11)
    assert c.routine.posts_to_like == 2
