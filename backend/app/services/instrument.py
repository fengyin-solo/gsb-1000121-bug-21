"""仪器管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "instrument"
REQUIRED_FIELDS = ["仪器编号", "仪器名称", "型号规格"]
STATUS_ORDER = ["在用", "待校准", "校准中", "已停用", "已报废"]
ACTION_RULES = {"发起校准": "校准中", "完成校准": "在用", "停用仪器": "已停用"}
NEGATIVE_ACTIONS = ["停用仪器"]
# 每个动作允许的前置状态：单条与批量共用同一道防线，重复触发会被拦下，
# 不会把记录再流转一次，批量结果也不会越积越多。
ACTION_SOURCES = {
    "发起校准": {"在用", "待校准"},
    "完成校准": {"校准中"},
    "停用仪器": {"在用", "待校准", "校准中"},
}


class InstrumentService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("仪器编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测仪器 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于仪器管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        current = str(entry.get("status") or "")
        label = entry.get("仪器编号") or entry_id
        if current == target:
            return None, f"检测仪器 {label} 已处于「{target}」，无需重复{action}"
        if current not in ACTION_SOURCES[action]:
            return None, f"检测仪器 {label} 当前状态为「{current}」，不允许{action}"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"检测仪器已{action}"

    def run_batch_action(self, ids: list[Any], action: str) -> dict[str, Any]:
        """批量执行动作：id 去重后逐条流转，每条记录只反馈一次。

        已处于目标状态的记录记为“跳过”，重复提交同一批不会重复流转，
        每批返回的明细里每个 id 有且只有一条结论。
        """
        action = str(action or "").strip()
        if action not in ACTION_RULES:
            return self._batch_summary(False, f"动作「{action}」不属于仪器管理可执行范围", [])
        unique_ids = self._unique_ids(ids)
        if not unique_ids:
            return self._batch_summary(False, "请先勾选要处理的检测仪器", [])
        details: list[dict[str, Any]] = []
        for entry_id in unique_ids:
            entry, message = self.run_action(entry_id, action)
            if entry is not None:
                details.append({"id": entry_id, "仪器编号": entry.get("仪器编号"), "result": "成功", "message": message})
                continue
            existing = store.find(MODULE, entry_id)
            if existing is not None and str(existing.get("status") or "") == ACTION_RULES[action]:
                details.append({"id": entry_id, "仪器编号": existing.get("仪器编号"), "result": "跳过", "message": message})
            else:
                label = (existing or {}).get("仪器编号")
                details.append({"id": entry_id, "仪器编号": label, "result": "失败", "message": message})
        succeeded = sum(1 for item in details if item["result"] == "成功")
        skipped = sum(1 for item in details if item["result"] == "跳过")
        failed = sum(1 for item in details if item["result"] == "失败")
        message = f"批量{action}完成：成功 {succeeded} 条、跳过 {skipped} 条、失败 {failed} 条"
        return self._batch_summary(failed == 0, message, details)

    @staticmethod
    def _unique_ids(ids: list[Any]) -> list[int]:
        """把前端传来的 id 列表规整成有序去重的正整数序列，非法值直接丢弃。"""
        unique: list[int] = []
        seen: set[int] = set()
        for raw in ids or []:
            if isinstance(raw, bool):
                continue
            try:
                entry_id = int(raw)
            except (TypeError, ValueError):
                continue
            if entry_id <= 0 or entry_id in seen:
                continue
            seen.add(entry_id)
            unique.append(entry_id)
        return unique

    @staticmethod
    def _batch_summary(ok: bool, message: str, details: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "ok": ok,
            "message": message,
            "total": len(details),
            "succeeded": sum(1 for item in details if item["result"] == "成功"),
            "skipped": sum(1 for item in details if item["result"] == "跳过"),
            "failed": sum(1 for item in details if item["result"] == "失败"),
            "details": details,
        }
