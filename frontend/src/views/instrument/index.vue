<template>
  <section class="page" data-module="instrument">
    <header class="page-head">
      <div>
        <h2>仪器管理管理</h2>
        <p class="page-desc">维护检测仪器，围绕仪器编号、仪器名称、型号规格、所属实验室做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记检测仪器</button>
        <button class="btn" type="button" @click="exportRows">导出仪器管理清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <div class="batch-bar">
      <label class="filter-item">
        <span>批量动作</span>
        <select v-model="batchAction" :disabled="batchRunning">
          <option v-for="action in actions" :key="action" :value="action">{{ action }}</option>
        </select>
      </label>
      <button class="btn primary" type="button" :disabled="batchRunning" @click="runBatch">
        {{ batchRunning ? '批量处理中…' : `批量处理（已选 ${selectedIds.length} 条）` }}
      </button>
      <span class="batch-hint">勾选一或多条检测仪器后统一执行；已处理的记录重复提交会自动跳过</span>
    </div>

    <div v-if="batchSummary || batchDetails.length" class="batch-result">
      <p class="batch-summary">{{ batchSummary }}</p>
      <ul class="batch-details">
        <li v-for="item in batchDetails" :key="item.id" :class="`result-${resultClass(item.result)}`">
          <span class="detail-label">{{ item['仪器编号'] || `#${item.id}` }}</span>
          <span class="detail-result">{{ item.result }}</span>
          <span class="detail-message">{{ item.message }}</span>
        </li>
      </ul>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th class="check-col">
            <input
              type="checkbox"
              :checked="allChecked"
              :disabled="!rows.length || batchRunning"
              aria-label="全选当前页"
              @change="toggleAll"
            />
          </th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td class="check-col">
            <input
              type="checkbox"
              :checked="selectedIds.includes(Number(row.id))"
              :disabled="batchRunning"
              :aria-label="`选择 ${row['仪器编号'] ?? row.id}`"
              @change="toggleOne(Number(row.id))"
            />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="batchRunning || actingId !== null"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无仪器管理数据，可先登记检测仪器</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条仪器管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

interface BatchDetail {
  id: number
  仪器编号?: string | null
  result: string
  message: string
}

const ENDPOINT = '/api/instrument'
const BATCH_TIMEOUT_MS = 10000
const columns = ["仪器编号", "仪器名称", "型号规格", "所属实验室", "校准周期", "上次校准日", "下次校准日", "仪器状态"]
const actions = ["发起校准", "完成校准", "停用仪器"]
const statuses = ["在用", "待校准", "校准中", "已停用", "已报废"]
const stats = [{"label": "在用仪器", "value": 0}, {"label": "待校准仪器", "value": 0}, {"label": "停用仪器", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const selectedIds = ref<number[]>([])
const batchAction = ref(actions[0])
const batchRunning = ref(false)
const actingId = ref<number | null>(null)
const batchSummary = ref('')
const batchDetails = ref<BatchDetail[]>([])

const allChecked = computed(
  () => rows.value.length > 0 && rows.value.every((row) => selectedIds.value.includes(Number(row.id))),
)

function resultClass(result: string) {
  if (result === '成功') return 'ok'
  if (result === '跳过') return 'skip'
  return 'fail'
}

function toggleAll() {
  selectedIds.value = allChecked.value ? [] : rows.value.map((row) => Number(row.id))
}

function toggleOne(id: number) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((item) => item !== id)
    : [...selectedIds.value, id]
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '检测仪器登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  if (actingId.value !== null || batchRunning.value) {
    return
  }
  errorMessage.value = ''
  actingId.value = Number(row.id)
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? '仪器管理动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '仪器管理操作失败'
  } finally {
    actingId.value = null
  }
}

async function runBatch() {
  // 每批先清空上一批的明细，保证页面上的结论只属于当前这一批
  errorMessage.value = ''
  batchSummary.value = ''
  batchDetails.value = []
  if (!selectedIds.value.length) {
    errorMessage.value = '请先勾选要处理的检测仪器'
    return
  }
  if (batchRunning.value) {
    return
  }
  batchRunning.value = true
  try {
    const response = await request(
      `${ENDPOINT}/batch`,
      {
        method: 'POST',
        body: JSON.stringify({ ids: selectedIds.value, action: batchAction.value }),
      },
      BATCH_TIMEOUT_MS,
    )
    const payload = await response.json()
    if (!response.ok) {
      throw new Error('批量处理请求被拒绝，请稍后重试')
    }
    // 明细按 id 去重：每条记录在本批结果里有且只有一条结论
    const seen = new Set<number>()
    batchDetails.value = ((payload.details ?? []) as BatchDetail[]).filter((item) => {
      if (seen.has(item.id)) {
        return false
      }
      seen.add(item.id)
      return true
    })
    batchSummary.value = payload.message ?? ''
    const failureMessage = payload.ok ? '' : payload.message ?? '批量处理未完全成功，请查看逐条明细'
    selectedIds.value = []
    await reload()
    // reload 会清空 errorMessage，部分失败的提示要在刷新后再落上去
    if (failureMessage) {
      errorMessage.value = failureMessage
    }
  } catch (error) {
    const detail = error instanceof Error ? error.message : '批量处理失败'
    await reload()
    errorMessage.value = `${detail}；请刷新列表核对状态，已处理的记录不会重复执行`
  } finally {
    batchRunning.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('检测仪器列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '仪器管理列表读取失败'
  }
}

onMounted(reload)
</script>
