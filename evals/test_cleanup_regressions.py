"""Database regressions. Requires TEST_DATABASE_URL pointing to a disposable pgvector DB.

Run from the repo root: python -m unittest discover -s evals -p test_cleanup_regressions.py -v
Each test rolls back its own outer transaction, including endpoint commits.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy.orm import Session

if not os.environ.get("TEST_DATABASE_URL"):
    raise unittest.SkipTest("Set TEST_DATABASE_URL to a disposable pgvector database")
os.environ.update(DATABASE_URL=os.environ["TEST_DATABASE_URL"], LLM_PROVIDER="mock",
                  EMBEDDINGS_PROVIDER="mock", EMBEDDINGS_ENABLED="false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from app import authoring, cleanup, main, models, retrieval  # noqa: E402
from app.db import engine, init_db  # noqa: E402


class CleanupRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def setUp(self):
        self.connection = engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(self.connection, join_transaction_mode="create_savepoint",
                          autoflush=False, expire_on_commit=False)

    def tearDown(self):
        self.db.close()
        self.transaction.rollback()
        self.connection.close()

    def entity(self, eid, name="Opening hours", attrs=None, enabled=True):
        e = models.KbEntity(id=eid, type="Hours", name=name, attributes=attrs or {},
                            sources=["test"], enabled=enabled)
        self.db.add(e)
        self.db.flush()
        return e

    def override(self, target, eid="override"):
        authoring.apply(self.db, [dict(action="add", entity_id=eid, entity_type="Hours",
            name=eid, field="opens", new_value="08:00", body="Open at 8am.",
            supersedes=target.id, is_conflict=False)], actor="Test")
        return self.db.get(models.KbEntity, eid)

    def test_blank_expiry_is_retained_and_searchable(self):
        e = self.entity("blank", attrs={"expires": "", "body": "Opening hours"})
        result = cleanup.sweep_expired(self.db)
        self.assertNotIn(e.id, result["removed"])
        self.assertIsNotNone(retrieval.get_entity(self.db, e.id))
        self.assertIn(e.id, [h["id"] for h in retrieval.search_graph(self.db, "opening")])

    def test_edit_normalizes_blank_expiry(self):
        self.entity("edit")
        main.update_entity("edit", main.EntityPatchRequest(attributes={"expires": "  "}), self.db)
        self.assertNotIn("expires", self.db.get(models.KbEntity, "edit").attributes)

    def test_invalid_expiry_is_rejected_on_edit(self):
        from pydantic import ValidationError
        for value in ("2026-02-30", "tomorrow", 12):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                main.EntityPatchRequest(attributes={"expires": value})

    def test_invalid_authoring_expiry_is_rejected_before_any_write(self):
        from pydantic import ValidationError
        changes = [dict(action="add", entity_id="bad", entity_type="Hours", name="Bad",
                        field="body", new_value="A fact", expires="not-a-date")]
        with self.assertRaises(ValidationError):
            main.AuthorApplyRequest(changes=changes)
        with self.assertRaises(ValueError):
            authoring.apply(self.db, changes, actor="Test")
        self.assertIsNone(self.db.get(models.KbEntity, "bad"))

    def test_authoring_can_clear_expiry(self):
        e = self.entity("temporary", attrs={"expires": "2099-01-01"})
        authoring.apply(self.db, [dict(action="update", entity_id=e.id, entity_type=e.type,
            name=e.name, field="body", new_value="Permanent fact", expires=None)], actor="Test")
        self.assertNotIn("expires", e.attributes)

    def test_invalid_legacy_expiry_is_never_deleted(self):
        e = self.entity("invalid", attrs={"expires": "0000-00-00"})
        cleanup.sweep_expired(self.db)
        self.assertIsNotNone(self.db.get(models.KbEntity, e.id))
        self.assertIsNone(retrieval.get_entity(self.db, e.id))

    def test_same_name_conflict_is_not_a_duplicate(self):
        self.entity("a", attrs={"opens": "07:00", "body": "Open at 7am."})
        self.entity("b", attrs={"opens": "08:00", "body": "Open at 8am."})
        self.assertEqual([], cleanup.RedundancyCheck().scan(self.db, "quick"))
        self.assertEqual(1, len(cleanup.ContradictionCheck().scan(self.db, "quick")))

    def test_identical_body_does_not_hide_structured_conflict(self):
        self.entity("a", attrs={"opens": "07:00", "body": "Opening hours"})
        self.entity("b", attrs={"opens": "08:00", "body": "Opening hours"})
        self.assertEqual([], cleanup.RedundancyCheck().scan(self.db, "quick"))

    def test_true_duplicate_is_still_detected(self):
        self.entity("a", attrs={"body": "Open at 7am."})
        self.entity("b", attrs={"body": "Open at 7am."})
        self.assertEqual(1, len(cleanup.RedundancyCheck().scan(self.db, "quick")))

    def test_undo_override_creation_restores_handbook(self):
        target = self.entity("hb-original")
        e = self.override(target)
        entry = self.db.scalar(select(models.ChangelogEntry).where(models.ChangelogEntry.entity_id == e.id))
        main.revert_change(str(entry.id), main.ActorRequest(), self.db)
        self.assertTrue(target.enabled)
        self.assertIsNone(self.db.get(models.KbEntity, e.id))

    def test_delete_one_of_two_overrides_keeps_original_disabled(self):
        target = self.entity("hb-original")
        self.override(target, "a")
        self.override(target, "b")
        main.delete_entity("a", main.ActorRequest(), self.db)
        self.assertFalse(target.enabled)
        main.delete_entity("b", main.ActorRequest(), self.db)
        self.assertTrue(target.enabled)

    def test_disable_and_reenable_override(self):
        target = self.entity("hb-original")
        e = self.override(target)
        main.set_entity_enabled(e.id, main.EnabledRequest(enabled=False), self.db)
        self.assertTrue(target.enabled)
        main.set_entity_enabled(e.id, main.EnabledRequest(enabled=True), self.db)
        self.assertFalse(target.enabled)

    def test_disable_one_of_two_overrides_keeps_original_disabled(self):
        target = self.entity("hb-original")
        self.override(target, "a")
        self.override(target, "b")
        main.set_entity_enabled("a", main.EnabledRequest(enabled=False), self.db)
        self.assertFalse(target.enabled)

    def test_enabling_superseded_original_is_blocked(self):
        target = self.entity("hb-original")
        self.override(target)
        with self.assertRaises(main.HTTPException) as error:
            main.set_entity_enabled(target.id, main.EnabledRequest(enabled=True), self.db)
        self.assertEqual(409, error.exception.status_code)

    def test_undo_disable_suppresses_original_again(self):
        target = self.entity("hb-original")
        e = self.override(target)
        main.set_entity_enabled(e.id, main.EnabledRequest(enabled=False), self.db)
        entry = self.db.scalar(select(models.ChangelogEntry).where(models.ChangelogEntry.action == "Disabled override"))
        main.revert_change(str(entry.id), main.ActorRequest(), self.db)
        self.assertTrue(e.enabled)
        self.assertFalse(target.enabled)

    def test_undo_delete_restores_supersession(self):
        target = self.entity("hb-original")
        e = self.override(target)
        main.delete_entity(e.id, main.ActorRequest(), self.db)
        entry = self.db.scalar(select(models.ChangelogEntry).where(models.ChangelogEntry.action == "Removed override"))
        main.revert_change(str(entry.id), main.ActorRequest(), self.db)
        self.assertFalse(target.enabled)
        main.set_entity_enabled(e.id, main.EnabledRequest(enabled=False), self.db)
        self.assertTrue(target.enabled)

    def test_expiration_restores_original_on_retrieval(self):
        past = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        target = self.entity("hb-original", attrs={"body": "Opening hours"})
        e = self.override(target)
        e.attributes = {"expires": past}
        self.db.flush()
        self.assertIsNotNone(retrieval.get_entity(self.db, target.id))
        self.assertIsNone(retrieval.get_entity(self.db, e.id))
        self.assertIn(target.id, [h["id"] for h in retrieval.search_graph(self.db, "opening")])

    def test_expiry_is_inclusive_through_today(self):
        today = datetime.now(timezone.utc).date().isoformat()
        e = self.entity("today", attrs={"expires": today})
        self.assertIsNotNone(retrieval.get_entity(self.db, e.id))

    def test_expiring_one_of_two_overrides_keeps_original_disabled(self):
        target = self.entity("hb-original")
        a = self.override(target, "a")
        self.override(target, "b")
        a.attributes = {"expires": "2020-01-01"}
        self.db.flush()
        cleanup.sweep_expired(self.db)
        self.assertFalse(target.enabled)
        self.assertIsNotNone(retrieval.get_entity(self.db, "b"))

    def test_neighbors_restore_expired_override_and_exclude_disabled_facts(self):
        source = self.entity("source")
        target = self.entity("hb-original", attrs={"body": "Opening hours"})
        self.entity("disabled", enabled=False)
        e = self.override(target)
        e.attributes = {"expires": "2020-01-01"}
        for eid in (target.id, e.id, "disabled"):
            self.db.add(models.KbRelationship(rel="related", src_id=source.id, dst_id=eid))
        self.db.flush()
        self.assertEqual([target.id], [h["id"] for h in retrieval.expand_neighbors(self.db, source.id)])

    def test_hybrid_search_uses_same_expiry_rules(self):
        vector = [1.0] + [0.0] * (retrieval.settings.embedding_dims - 1)
        for eid, attrs, enabled in [("blank", {"expires": ""}, True),
                                     ("invalid", {"expires": "bad-date"}, True),
                                     ("disabled", {}, False)]:
            e = self.entity(eid, attrs=attrs, enabled=enabled)
            e.embedding = vector
        self.db.flush()
        with patch.object(retrieval.settings, "embeddings_enabled", True), patch.object(retrieval, "embed_query", return_value=vector):
            self.assertEqual(["blank"], [h["id"] for h in retrieval.search_graph(self.db, "opening")])

    def test_retrieval_does_not_commit_callers_work(self):
        self.entity("hb-original", enabled=False)
        expired = self.entity("expired", attrs={"expires": "2020-01-01"})
        self.db.add(models.KbRelationship(rel="supersedes", src_id=expired.id, dst_id="hb-original"))
        self.db.flush()
        with patch.object(self.db, "commit", wraps=self.db.commit) as commit:
            retrieval.get_entity(self.db, "hb-original")
            commit.assert_not_called()

    def test_handbook_edit_and_delete_remain_blocked(self):
        self.entity("hb-original")
        for action in (lambda: main.update_entity("hb-original", main.EntityPatchRequest(name="Changed"), self.db),
                       lambda: main.delete_entity("hb-original", main.ActorRequest(), self.db)):
            with self.assertRaises(main.HTTPException) as error:
                action()
            self.assertEqual(409, error.exception.status_code)


if __name__ == "__main__":
    unittest.main()
