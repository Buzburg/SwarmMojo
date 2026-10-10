from pathlib import Path
import tempfile
import unittest

from aeon.conversations import Conversations
from aeon.memory import Memory


class ConversationSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.memory = Memory(self.root/'state')
        self.store = Conversations(self.memory, self.root/'work')
        self.cid = self.store.create()

    def tearDown(self):
        self.memory.close()
        self.temp.cleanup()

    def test_old_entry_context_and_revision(self):
        old = self.store.append(self.cid, 'note', 'Orchid launch uses violet')
        for i in range(220):
            self.store.append(self.cid, 'note', f'Unrelated entry {i}')
        self.assertIn(old, [r['id'] for r in self.store.context(self.cid, 'Orchid')['entries']])
        new = self.store.append(self.cid, 'correction', 'Orchid launch uses green', replaces=old)
        self.assertEqual([r['id'] for r in self.store.search(self.cid, 'Orchid')['entries']], [new])
        self.assertEqual(self.store.search(self.cid, 'violet')['entries'], [])
        self.assertIsNotNone(self.memory.db.execute('SELECT id FROM conversation_entries WHERE id=?', (old,)).fetchone())

    def test_migration_restart_and_scope(self):
        old = self.store.append(self.cid, 'note', 'Legacy mango record')
        self.memory.db.execute('DROP TRIGGER conversation_search_insert')
        self.memory.db.execute('DROP TABLE conversation_search')
        self.memory.db.commit()
        self.store = Conversations(self.memory, self.root/'work')
        self.assertEqual(self.store.search(self.cid, 'mango')['entries'][0]['id'], old)
        other = self.store.create()
        self.assertEqual(self.store.search(other, 'mango')['entries'], [])
        with self.assertRaises(ValueError):
            Conversations(self.memory, self.root/'elsewhere').search(self.cid, 'mango')
        self.memory.close()
        self.memory = Memory(self.root/'state')
        store = Conversations(self.memory, self.root/'work')
        store.append(self.cid, 'note', 'New mango record')
        self.assertEqual(len(store.search(self.cid, 'mango')['entries']), 2)
        self.memory.db.execute('DROP TRIGGER conversation_search_insert')
        store.append(self.cid, 'note', 'Inserted while indexing unavailable')
        store = Conversations(self.memory, self.root/'work')
        self.assertEqual(len(store.search(self.cid, 'unavailable')['entries']), 1)

    def test_literal_queries_bounds_and_fallback(self):
        self.store.append(self.cid, 'note', 'Café orchard')
        for fts in (True, False):
            self.store.fts = fts
            self.assertEqual(len(self.store.search(self.cid, '"café" OR (orchard*)')['entries']), 1)
            self.assertEqual(self.store.search(self.cid, '***')['entries'], [])
            with self.assertRaises(ValueError):
                self.store.search(self.cid, 'x', 51)
        self.assertEqual(self.store.search(self.cid, 'café')['mode'], 'lexical_latest_1000')
        with self.assertRaises(ValueError):
            self.store.search(self.cid, 'x'*16001)

    def test_fallback_current_revisions_and_budget(self):
        old = self.store.append(self.cid, 'note', 'Needle wrong')
        new = self.store.append(self.cid, 'correction', 'Needle right', replaces=old)
        self.store.fts = False
        self.assertEqual([r['id'] for r in self.store.search(self.cid, 'needle')['entries']], [new])
        for i in range(10):
            self.store.append(self.cid, 'note', 'Needle ' + 'z'*4000)
        context = self.store.context(self.cid, 'needle')
        from aeon.memory import packed
        self.assertLessEqual(sum(len(packed(r).encode()) for r in context['entries']), 8000)
