export type ExperimentArm = 'single_agent' | 'full'
export type CaseGroupId = 'legacy_compound' | 'conflict' | 'mislead' | 'single_domain'

export interface ExperimentArmSummary {
  arm: ExperimentArm
  configHash: string
  totalCases: number
  durationSeconds: number
  seed: number
  model: string
  judgeModel: string
  judgeIsStub: boolean
  errorCount: number
  rootCause: number
  keyPointsRecall: number
  routeHit: number
  latencyMs: number
  tokens: number
}

export interface CaseGroupMetric {
  id: CaseGroupId
  label: string
  description: string
  count: number
  singleAgent: number
  full: number
}

/**
 * M5 真实跑批的只读摘要。数值逐项核对自：
 * experiments/6f53f145fe33/{meta,summary}.json 与
 * experiments/a2752bd48380/{meta,summary}.json。
 * 原始产物受 .gitignore 保护，不由浏览器读取。
 */
export const M5_EXPERIMENTS: Record<ExperimentArm, ExperimentArmSummary> = {
  single_agent: {
    arm: 'single_agent',
    configHash: '6f53f145fe33',
    totalCases: 77,
    durationSeconds: 5839.46,
    seed: 42,
    model: 'deepseek-v4-flash',
    judgeModel: 'deepseek-v4-pro',
    judgeIsStub: false,
    errorCount: 0,
    rootCause: 0.551948051948052,
    keyPointsRecall: 0.5393939393939393,
    routeHit: 0.5844155844155844,
    latencyMs: 75837.09357792203,
    tokens: 12452.142857142857,
  },
  full: {
    arm: 'full',
    configHash: 'a2752bd48380',
    totalCases: 77,
    durationSeconds: 5891.24,
    seed: 42,
    model: 'deepseek-v4-flash',
    judgeModel: 'deepseek-v4-pro',
    judgeIsStub: false,
    errorCount: 0,
    rootCause: 0.7142857142857142,
    keyPointsRecall: 0.7216450216450213,
    routeHit: 0.8961038961038961,
    latencyMs: 76509.40997142842,
    tokens: 20000.285714285714,
  },
}

export const M5_CASE_GROUPS: CaseGroupMetric[] = [
  { id: 'legacy_compound', label: '跨源复合', description: 'legacy_compound', count: 20, singleAgent: 0.27, full: 0.765 },
  { id: 'conflict', label: '真分歧 + 辩论', description: 'conflict', count: 6, singleAgent: 0.4166666666666667, full: 0.7333333333333334 },
  { id: 'mislead', label: '表象误导', description: 'mislead', count: 6, singleAgent: 0.5833333333333334, full: 0.5833333333333334 },
  { id: 'single_domain', label: '单域故障', description: 'single_domain', count: 45, singleAgent: 0.691111111111111, full: 0.7066666666666667 },
]

export function percent(value: number, digits = 0): number {
  return Number((value * 100).toFixed(digits))
}

export function percentagePointDelta(before: number, after: number, digits = 1): number {
  return Number(((after - before) * 100).toFixed(digits))
}

export function relativeChange(before: number, after: number, digits = 0): number {
  if (before === 0) return 0
  return Number((((after - before) / before) * 100).toFixed(digits))
}

export function secondsFromMs(milliseconds: number): number {
  return Number((milliseconds / 1000).toFixed(1))
}

export function formatDelta(value: number, suffix = 'pp'): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}${suffix}`
}
