"""仪器管理批量处理与状态守卫的回归测试。

覆盖：多选批量逐条生效、空选、部分失败、重复提交幂等、明细唯一、
边界冲突后列表与详情结论一致，以及导出入口不再被详情路由遮蔽。
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def batch(ids, action):
    return client.post("/api/instrument/batch", json={"ids": ids, "action": action})


def detail_status(entry_id):
    return client.get(f"/api/instrument/{entry_id}").json()["status"]


def list_status(entry_id):
    items = client.get("/api/instrument", params={"size": 200}).json()["items"]
    return next(row["status"] for row in items if row["id"] == entry_id)


def test_batch_applies_to_every_selected_record():
    # 种子里 1=在用、2=待校准、3=校准中；对三条一起发起校准
    resp = batch([1, 2, 3], "发起校准")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["total"] == 3
    assert payload["succeeded"] == 2  # 前两条都生效，不是只有第一条
    assert payload["skipped"] == 1  # 第三条已在校准中，自动跳过
    assert payload["failed"] == 0
    assert [item["id"] for item in payload["details"]] == [1, 2, 3]
    assert detail_status(1) == detail_status(2) == "校准中"


def test_batch_empty_selection_changes_nothing():
    payload = batch([], "发起校准").json()
    assert payload["ok"] is False
    assert payload["total"] == 0
    assert payload["details"] == []
    assert "勾选" in payload["message"]
    assert detail_status(1) == "在用"  # 空选不应改动任何记录


def test_batch_dedupes_ids_and_details_are_unique():
    payload = batch([1, 1, 2, 2, 1], "发起校准").json()
    assert payload["total"] == 2
    ids = [item["id"] for item in payload["details"]]
    assert sorted(ids) == [1, 2]
    assert len(ids) == len(set(ids))  # 每批明细数量唯一，不会多出


def test_batch_partial_failure_reports_each_item():
    payload = batch([1, 999], "发起校准").json()
    assert payload["ok"] is False
    assert payload["succeeded"] == 1
    assert payload["failed"] == 1
    by_id = {item["id"]: item for item in payload["details"]}
    assert by_id[1]["result"] == "成功"
    assert by_id[999]["result"] == "失败"
    assert "不存在" in by_id[999]["message"]
    assert detail_status(1) == "校准中"  # 部分失败不影响可处理的记录


def test_batch_repeat_submission_is_idempotent():
    first = batch([1, 2], "发起校准").json()
    assert first["succeeded"] == 2
    second = batch([1, 2], "发起校准").json()
    assert second["succeeded"] == 0
    assert second["skipped"] == 2  # 重复提交全部跳过，不会重复执行
    assert second["total"] == 2  # 每批明细仍然唯一，旧结果不累加
    assert all(item["result"] == "跳过" for item in second["details"])
    assert detail_status(1) == detail_status(2) == "校准中"


def test_batch_rejects_invalid_ids_and_unknown_action():
    payload = batch([-1, 0], "发起校准").json()
    assert payload["ok"] is False
    assert payload["total"] == 0  # 非法 id 被丢弃后按空选处理
    payload = batch([1], "删除仪器").json()
    assert payload["ok"] is False
    assert payload["details"] == []
    assert detail_status(1) == "在用"


def test_single_action_conflict_then_two_views_agree():
    # 先把 2 停用，再对它发起校准：边界冲突
    stop = client.post("/api/instrument/2/actions", json={"values": {"action": "停用仪器"}}).json()
    assert stop["ok"] is True
    conflict = client.post("/api/instrument/2/actions", json={"values": {"action": "发起校准"}}).json()
    assert conflict["ok"] is False
    assert "已停用" in conflict["message"]
    # 边界冲突后再次操作，结论不变；列表页与详情页显示相同状态
    again = client.post("/api/instrument/2/actions", json={"values": {"action": "发起校准"}}).json()
    assert again["ok"] is False
    assert again["message"] == conflict["message"]
    assert list_status(2) == detail_status(2) == "已停用"


def test_single_action_repeat_same_target_is_rejected():
    first = client.post("/api/instrument/1/actions", json={"values": {"action": "发起校准"}}).json()
    assert first["ok"] is True
    second = client.post("/api/instrument/1/actions", json={"values": {"action": "发起校准"}}).json()
    assert second["ok"] is False
    assert "无需重复" in second["message"]
    assert list_status(1) == detail_status(1) == "校准中"


def test_export_route_not_shadowed_by_detail():
    resp = client.get("/api/instrument/export")
    assert resp.status_code == 200
    assert resp.json()["module"] == "instrument"
