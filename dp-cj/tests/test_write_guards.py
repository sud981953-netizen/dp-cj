"""No live writes: exercise category, industry and attachment failure behavior."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import write_record as w
import douyin_transcript as d


def record(*tokens):
    return {"ok": True, "data": {"data": [[[{'file_token': t} for t in tokens]]]}}


class WriteGuards(unittest.TestCase):
    def setUp(self):
        self.fields = [{"name": "行业", "type": "select", "multiple": False,
                        "options": [{"name": n} for n in ["餐饮", "服装", "门窗"]]},
                       {"name": "封面", "type": "attachment"}, {"name": "链接", "type": "text"}]
        self.mapping = {"industry": "行业", "cover": "封面", "copy_type": "文案类型", "source_url": "链接"}
        self.payload = {"full_text": "我开火锅店，每天备菜到深夜。", "industry": "火锅店",
                        "industry_evidence": "我开火锅店"}

    def test_seventh_category_does_not_replace_old_emotion(self):
        self.assertEqual(w.normalize_category("2"), "情感(泛流量)")
        self.assertEqual(w.normalize_category("7"), "情感共鸣型（泛流量）")
        self.assertEqual(w.normalize_category("情感共鸣型(泛流量)"), w.normalize_category("7"))

    def test_industry_normalizes_and_missing_fields_are_omitted(self):
        mapping = w.prepare_fields(self.payload, self.mapping, self.fields)
        self.assertEqual(self.payload["industry"], "餐饮")
        self.assertNotIn("copy_type", mapping)
        self.assertEqual(w.remap_payload(self.payload, mapping), {"行业": "餐饮"})

    def test_incidental_food_does_not_override_business(self):
        p = {"full_text": "我做女装，收摊后去吃火锅。", "industry": "服装", "industry_evidence": "我做女装"}
        w.prepare_fields(p, self.mapping, self.fields)
        self.assertEqual(p["industry"], "服装")

    def test_rejects_unknown_array_and_fabricated_evidence(self):
        for change in [{"industry": "实体店"}, {"industry": ["餐饮", "门窗"]},
                       {"industry_evidence": "我开门窗厂"}, {"industry_evidence": ""}]:
            with self.subTest(change=change), self.assertRaises(w.ConfigError):
                w.prepare_fields({**self.payload, **change}, self.mapping, self.fields)

    def test_undetermined_preserves_old_industry_by_omitting_patch(self):
        p = {"full_text": "学会与自己和解", "industry_status": "undetermined", "industry_reason": "没有主营业务事实"}
        mapping = w.prepare_fields(p, self.mapping, self.fields)
        self.assertNotIn("行业", w.remap_payload(p, mapping))
        with self.assertRaises(w.ConfigError):
            w.prepare_fields({"full_text": "缺少判断步骤"}, self.mapping, self.fields)

    def test_rejects_multiselect_schema(self):
        self.fields[0]["multiple"] = True
        with self.assertRaises(w.ConfigError):
            w.prepare_fields(self.payload, self.mapping, self.fields)

    def test_unverified_cover_blocked_and_verified_cover_allowed(self):
        p = {**self.payload, "cover": "test.jpg"}
        with self.assertRaises(w.ConfigError):
            w.prepare_fields(p, self.mapping, self.fields)
        p.update(cover_verified=True, cover_source="dynamic_cover", cover_verification_note="同作品 ID、人物场景核对通过")
        w.prepare_fields(p, self.mapping, self.fields)
        p["cover_source"] = "origin_cover"
        with self.assertRaises(w.ConfigError):
            w.prepare_fields(p, self.mapping, self.fields)

    def test_wrong_work_id_rejected(self):
        with self.assertRaises(ValueError):
            d.parse_detail({"aweme_detail": {"aweme_id": "999"}}, "推荐视频", expected_id="123")
        result = d.parse_detail({"aweme_detail": {"aweme_id": "123"}}, "目标", expected_id="123")
        self.assertEqual(result["cover_url"], "")

    def replace(self, responses, materialized=(Path("verified.jpg"), "local")):
        with patch.object(w, "materialize_attachment", return_value=materialized), patch.object(w, "run_cli", side_effect=responses) as cli:
            result = w.replace_attachment({"cover": "verified.jpg"}, "cover", "封面", "rec1",
                                          {"table_id": "tbl1"}, {"base_token": "test"}, {}, Path("config.json"))
            return result, [c.args[0][1] for c in cli.call_args_list]

    def test_download_failure_preserves_old_attachment(self):
        result, calls = self.replace([], (None, "download_failed"))
        self.assertFalse(result["ok"])
        self.assertEqual(calls, [])

    def test_upload_failure_never_removes_old(self):
        result, calls = self.replace([record("old"), {"ok": False}])
        self.assertFalse(result["ok"])
        self.assertNotIn("+record-remove-attachment", calls)

    def test_success_upload_then_remove_then_verify(self):
        result, calls = self.replace([record("old"), {"ok": True}, record("old", "new"), {"ok": True}, record("new")])
        self.assertTrue(result["ok"])
        self.assertEqual(calls, ["+record-get", "+record-upload-attachment", "+record-get", "+record-remove-attachment", "+record-get"])

    def test_report_failure_when_old_attachment_still_present(self):
        result, _ = self.replace([record("old"), {"ok": True}, record("old", "new"), {"ok": True}, record("old", "new")])
        self.assertFalse(result["ok"])

    def test_failed_dedupe_is_not_no_match(self):
        with patch.object(w, "run_cli", return_value={"ok": False}), self.assertRaises(w.ConfigError):
            w.find_existing("https://example.com", {"table_id": "tbl1", "dedupe_field": "链接"}, {"base_token": "test"})


if __name__ == "__main__":
    unittest.main()
