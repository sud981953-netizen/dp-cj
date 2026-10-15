import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from migrate_config import migrate_config


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "config.json"
        self.cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        self.cfg["workspace_root"] = "CUSTOM_WORKSPACE"
        self.cfg["python_executable"] = "CUSTOM_PYTHON"
        self.cfg["user_custom_setting"] = {"keep": True}
        self.cfg["routing"]["options"].remove("情感共鸣型（泛流量）")
        del self.cfg["feishu"]["tables"]["情感共鸣型（泛流量）"]
        del self.cfg["feishu"]["tables"]["工厂实体店"]["field_map"]["industry"]

    def save(self):
        self.path.write_text(json.dumps(self.cfg, ensure_ascii=False), encoding="utf-8")

    def test_old_install_migrates_and_preserves_all_existing_values(self):
        self.save()
        original_bytes = self.path.read_bytes()
        self.assertTrue(migrate_config(self.path))
        result = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(result["routing"]["options"][-1], "情感共鸣型（泛流量）")
        self.assertEqual(result["feishu"]["tables"]["工厂实体店"]["field_map"]["industry"], "行业")
        self.assertEqual(result["feishu"]["tables"]["情感共鸣型（泛流量）"]["table_id"], "tblbnZuCHc3K7qDc")
        rollback = copy.deepcopy(result)
        rollback["routing"]["options"].pop()
        del rollback["feishu"]["tables"]["情感共鸣型（泛流量）"]
        del rollback["feishu"]["tables"]["工厂实体店"]["field_map"]["industry"]
        self.assertEqual(rollback, self.cfg)
        self.assertEqual(self.path.with_name("config.json.pre-v1.4.0.bak").read_bytes(), original_bytes)
        self.assertFalse(migrate_config(self.path))

    def test_other_base_is_untouched(self):
        self.cfg["feishu"]["base_token"] = "another-base"
        self.save()
        before = self.path.read_bytes()
        self.assertFalse(migrate_config(self.path))
        self.assertEqual(self.path.read_bytes(), before)

    def test_existing_custom_industry_mapping_is_preserved(self):
        self.cfg["feishu"]["tables"]["工厂实体店"]["field_map"]["industry"] = "客户行业"
        self.save()
        migrate_config(self.path)
        result = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(result["feishu"]["tables"]["工厂实体店"]["field_map"]["industry"], "客户行业")


if __name__ == "__main__":
    unittest.main()
