import { describe, expect, it } from 'vitest'

import { batchInspectionItems, filterBatchItems, sortBatchItems } from './batchInspection'

describe('batch inspection data helpers', () => {
  it('searches source names and metadata', () => {
    expect(filterBatchItems(batchInspectionItems, 'Recovery', 'all', 'all').map((item) => item.id)).toEqual(['C-42'])
    expect(filterBatchItems(batchInspectionItems, '50', 'all', 'all').map((item) => item.id)).toEqual(['D-50'])
  })

  it('filters failures, scientific warnings, anomalies and export exclusions', () => {
    expect(filterBatchItems(batchInspectionItems, '', 'failed', 'all').map((item) => item.id)).toEqual(['D-50'])
    expect(filterBatchItems(batchInspectionItems, '', 'all', 'scientific-warning').map((item) => item.id)).toEqual(['B-37'])
    expect(filterBatchItems(batchInspectionItems, '', 'all', 'anomaly').map((item) => item.id)).toEqual(['C-42'])
    expect(filterBatchItems(batchInspectionItems, '', 'all', 'excluded').map((item) => item.id)).toEqual(['C-42', 'D-50'])
  })

  it('sorts by updated time, source, metadata and status', () => {
    expect(sortBatchItems(batchInspectionItems, 'updated-desc')[0].id).toBe('A-25')
    expect(sortBatchItems(batchInspectionItems, 'source-asc')[0].id).toBe('A-25')
    expect(sortBatchItems(batchInspectionItems, 'temperature-asc').map((item) => item.temperature)).toEqual([25, 37, 42, 50])
    expect(sortBatchItems(batchInspectionItems, 'status')[0].status).toBe('failed')
  })
})
