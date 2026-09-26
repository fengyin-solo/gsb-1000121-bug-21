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
      <span class="batch-summary">已选 {{ selectedIds.length }} 条检测仪器</span>
      <button
        v-for="action in actions"
        :key="action"
        class="btn"
        type="button"
        :disabled="submitting"
        @click="runBatchAction(action)"
      >
        批量{{ action }}
      </button>
      <span v-if="submitting" class="batch-hint">批量处理中，请勿重复提交…</span>
    </div>

    <table class="data-table">
      <thead>
        <tr>
          <th>
            <input
              type="checkbox"
              :checked="allSelected"
              :disabled="!rows.length || submitting"
              @change="toggleSelectAll"
            />
          </th>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>
            <input
              type="checkbox"
              :checked="selectedSet.has(Number(row.id))"
              :disabled="submitting"
              @change="toggleSelect(row.id)"
            />
          </td>
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="submitting"
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

    <section v-if="batchResult" class="batch-result">
      <header class="batch-result-head">
        <strong>{{ batchResult.message }}</strong>
        <span>共 {{ batchResult.total }} 条：成功 {{ batchResult.succeeded }} 条，未生效 {{ batchResult.failed }} 条</span>
      </header>
      <ul class="batch-result-list">
        <li v-for="item in batchResult.items" :key="item.id" :class="item.ok ? 'ok' : 'fail'">
          {{ item.message }}
        </li>
      </ul>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条仪器管理记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type BatchItem = { id: number; ok: boolean; message: string }
type BatchResult = {
  ok: boolean
  message: string
  total: number
  succeeded: number
  failed: number
  items: BatchItem[]
}

const ENDPOINT = '/api/instrument'
const REQUEST_TIMEOUT = 10000
const columns = ["仪器编号", "仪器名称", "型号规格", "所属实验室", "校准周期", "上次校准日", "下次校准日", "仪器状态"]
const actions = ["发起校准", "完成校准", "停用仪器"]
const statuses = ["在用", "待校准", "校准中", "已停用", "已报废"]
const stats = [{"label": "在用仪器", "value": 0}, {"label": "待校准仪器", "value": 0}, {"label": "停用仪器", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)
const selectedIds = ref<number[]>([])
const submitting = ref(false)
const batchResult = ref<BatchResult | null>(null)

const selectedSet = computed(() => new Set(selectedIds.value))
const allSelected = computed(
  () => rows.value.length > 0 && rows.value.every((row) => selectedSet.value.has(Number(row.id))),
)

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

function toggleSelect(id: Row['id']) {
  const numId = Number(id)
  if (selectedSet.value.has(numId)) {
    selectedIds.value = selectedIds.value.filter((item) => item !== numId)
  } else {
    selectedIds.value = [...selectedIds.value, numId]
  }
}

function toggleSelectAll() {
  if (allSelected.value) {
    const pageIds = new Set(rows.value.map((row) => Number(row.id)))
    selectedIds.value = selectedIds.value.filter((id) => !pageIds.has(id))
  } else {
    selectedIds.value = [...new Set([...selectedIds.value, ...rows.value.map((row) => Number(row.id))])]
  }
}

function runAction(action: string, row: Row) {
  void submitAction(action, [Number(row.id)])
}

function runBatchAction(action: string) {
  void submitAction(action, [...selectedIds.value])
}

/** 单条与批量共用的唯一提交入口：在途守卫防重复触发，超时可中断，逐条反馈按 id 去重。 */
async function submitAction(action: string, ids: number[]) {
  if (submitting.value) {
    return
  }
  if (!ids.length) {
    errorMessage.value = '请先勾选需要处理的检测仪器'
    return
  }
  submitting.value = true
  errorMessage.value = ''
  noticeMessage.value = ''
  batchResult.value = null
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT)
  try {
    const response = await request(`${ENDPOINT}/actions/batch`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ids } }),
      signal: controller.signal,
    })
    if (!response.ok) {
      throw new Error('仪器管理动作未生效，请稍后重试')
    }
    const payload = (await response.json()) as BatchResult
    const seen = new Set<number>()
    const items = (payload.items ?? []).filter((item) => {
      if (seen.has(item.id)) {
        return false
      }
      seen.add(item.id)
      return true
    })
    batchResult.value = { ...payload, items }
    noticeMessage.value = payload.message
    await reload()
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      errorMessage.value = '批量处理超时，请检查网络后重试'
    } else {
      errorMessage.value = error instanceof Error ? error.message : '仪器管理操作失败'
    }
  } finally {
    window.clearTimeout(timer)
    submitting.value = false
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
    const visible = new Set(rows.value.map((row) => Number(row.id)))
    selectedIds.value = selectedIds.value.filter((id) => visible.has(id))
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '仪器管理列表读取失败'
  }
}

onMounted(reload)
</script>
