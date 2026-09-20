"""Tests for db/biases.py"""

import pytest

from config import Database
from db.biases import (
    create_artist_bias_db, create_ultimate_bias_db, get_artist_bias, get_ultimate_bias,
    update_artist_bias_db, update_ultimate_bias_db
)


@pytest.fixture(autouse=True)
def _biases_database(databases):
    databases(Database.BIASES)


def _ultimate(user_id=1, **overrides):
    values = {"user_id": user_id, "name": "Seohyun", "birth_name": "Seo Juhyun", "birthday": "June 28, 1991",
              "colour": 0xFF4980, "group_name": "Girls' Generation", "hometown": "Seoul",
              "image_filename": "seohyun.jpg", "position": "Maknae", "reason": "Because"}
    values.update(overrides)
    return create_ultimate_bias_db(**values)


def _group(user_id=1, **overrides):
    values = {"user_id": user_id, "name": "IVE", "album": "Love Dive", "b_track": "Royalty", "bias": "Wonyoung",
              "colour": 0x123456, "debut_date": "Dec 1, 2021", "image_filename": "ive.jpg", "label": "Starship",
              "members": "Yujin, Gaeul", "reason": "Why not", "title_track": "Eleven"}
    values.update(overrides)
    return create_artist_bias_db(**values)


class TestUltimateBias:
    """One ultimate bias per member."""

    def test_none_before_one_is_created(self):
        assert get_ultimate_bias(1) is None

    def test_create_then_get_returns_every_field(self):
        assert _ultimate() is True

        assert get_ultimate_bias(1) == {
            "user_id": 1, "name": "Seohyun", "birth_name": "Seo Juhyun", "birthday": "June 28, 1991",
            "colour": 0xFF4980, "group_name": "Girls' Generation", "hometown": "Seoul",
            "image_filename": "seohyun.jpg", "position": "Maknae", "reason": "Because",
        }

    def test_a_member_cannot_have_two(self):
        _ultimate(name="first")

        assert _ultimate(name="second") is False
        assert get_ultimate_bias(1)["name"] == "first"

    def test_members_are_independent(self):
        _ultimate(user_id=1, name="a")
        _ultimate(user_id=2, name="b")

        assert get_ultimate_bias(2)["name"] == "b"

    def test_update_changes_only_the_given_fields(self):
        _ultimate()

        assert update_ultimate_bias_db(1, reason="New reason", colour=0x000001) is True

        row = get_ultimate_bias(1)
        assert (row["reason"], row["colour"]) == ("New reason", 1)
        assert row["name"] == "Seohyun"

    def test_update_for_a_member_without_one_is_false(self):
        assert update_ultimate_bias_db(1, reason="x") is False

    def test_update_with_nothing_to_change_is_false(self):
        _ultimate()

        assert update_ultimate_bias_db(1) is False

    def test_update_rejects_unknown_columns(self):
        # Column names go into the SQL text, so only the known ones may be used
        _ultimate()

        with pytest.raises(ValueError, match="Unknown bias columns"):
            update_ultimate_bias_db(1, **{"name = 'x', reason": "boom"})

        assert get_ultimate_bias(1)["name"] == "Seohyun"

    def test_the_two_kinds_of_bias_do_not_mix(self):
        _ultimate()

        assert get_artist_bias(1) is None
        with pytest.raises(ValueError):
            update_ultimate_bias_db(1, album="artist-only column")


class TestArtistBias:
    """One bias group per member."""

    def test_none_before_one_is_created(self):
        assert get_artist_bias(1) is None

    def test_create_then_get_returns_every_field(self):
        assert _group() is True

        assert get_artist_bias(1) == {
            "user_id": 1, "name": "IVE", "album": "Love Dive", "b_track": "Royalty", "bias": "Wonyoung",
            "colour": 0x123456, "debut_date": "Dec 1, 2021", "image_filename": "ive.jpg", "label": "Starship",
            "members": "Yujin, Gaeul", "reason": "Why not", "title_track": "Eleven",
        }

    def test_a_member_cannot_have_two(self):
        _group(name="first")

        assert _group(name="second") is False
        assert get_artist_bias(1)["name"] == "first"

    def test_update_changes_only_the_given_fields(self):
        _group()

        assert update_artist_bias_db(1, bias="Rei", label="New label") is True

        row = get_artist_bias(1)
        assert (row["bias"], row["label"], row["name"]) == ("Rei", "New label", "IVE")

    def test_update_for_a_member_without_one_is_false(self):
        assert update_artist_bias_db(1, bias="x") is False

    def test_update_with_nothing_to_change_is_false(self):
        _group()

        assert update_artist_bias_db(1) is False

    def test_update_rejects_unknown_columns(self):
        _group()

        with pytest.raises(ValueError, match="Unknown bias columns"):
            update_artist_bias_db(1, hometown="ultimate-only column")
