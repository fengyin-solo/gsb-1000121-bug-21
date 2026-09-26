"""仪器管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "instrument"
REQUIRED_FIELDS = ["仪器编号", "仪器名称", "型号规格"]
STATUS_FIELD = "仪器状态"
STATUS_ORDER = ["在用", "待校准", "校准中", "已停用", "已报废"]
ACTION_RULES = {"发起校准": "校准中", "完成校准": "在用", "停用仪器": "已停用"}
NEGATIVE_ACTIONS = ["停用仪器"]


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
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        """单条处理入口：详情动作与批量处理都走这里，同一记录同一结论。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测仪器 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于仪器管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if entry.get("status") == target:
            return None, f"检测仪器 {entry_id} 已处于「{target}」，请勿重复{action}"
        entry["status"] = target
        entry[STATUS_FIELD] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"检测仪器 {entry_id} 已{action}"

    def run_batch_action(self, entry_ids: list[Any], action: str) -> dict[str, Any]:
        """批量处理入口：动作只校验一次，id 去重保序，逐条走单条入口汇总反馈。"""
        action = str(action or "").strip()
        if action not in ACTION_RULES:
            return {"ok": False, "message": f"动作「{action}」不属于仪器管理可执行范围", "items": []}
        unique_ids = list(dict.fromkeys(self._coerce_id(raw) for raw in entry_ids))
        unique_ids = [uid for uid in unique_ids if uid is not None]
        if not unique_ids:
            return {"ok": False, "message": "未选择任何检测仪器，批量处理未执行", "items": []}
        items: list[dict[str, Any]] = []
        for uid in unique_ids:
            entry, message = self.run_action(uid, action)
            items.append({"id": uid, "ok": entry is not None, "message": message})
        succeeded = sum(1 for item in items if item["ok"])
        failed = len(items) - succeeded
        if failed == 0:
            message = f"批量{action}完成：{succeeded} 条全部成功"
        elif succeeded == 0:
            message = f"批量{action}完成：{failed} 条全部未生效"
        else:
            message = f"批量{action}完成：{succeeded} 条成功、{failed} 条未生效"
        return {"ok": failed == 0, "message": message, "items": items}

    @staticmethod
    def _coerce_id(raw: Any) -> int | None:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
