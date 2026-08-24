import { describe, expect, it } from 'vitest'

import type { JsonValue } from '../../../shared/desktop-contract'
import {
  disambiguateDatasetDisplayNames,
  readDurableTasks,
  readWorkflowPlan,
  readDatasets,
  readImportSummary,
  readWorkflowOutcome,
  readPlot,
  readPlots,
} from './productState'

describe('product plot state', () => {
  it('renders a cancelled Agent run as a no-change terminal outcome', () => {
    expect(readWorkflowOutcome({ outcome: 'cancelled', workflow_run_id: 'task:test' })).toEqual({
      kind: 'no_change',
      title: '任务已取消',
      message: '任务已停止，项目未发生更改。',
    })
  })

  it('renders a verified read-only Agent answer as information', () => {
    expect(readWorkflowOutcome({
      outcome: 'information_ready',
      workflow_run_id: 'task:inspection',
      message: '共有 4 列，其中 1 个值缺失。',
    })).toEqual({
      kind: 'information',
      title: '检查完成',
      message: '共有 4 列，其中 1 个值缺失。',
    })
  })

  it('prefers file and worksheet identity and summarizes per-file import outcomes', () => {
    const value: JsonValue = {
      selected_files: ['仪器记录.xlsx', '损坏.csv'],
      imports: [
        {
          kind: 'committed',
          source_file_name: '仪器记录.xlsx',
          datasets: [{
            source_dataset_id: 'source:opaque',
            source_file_name: '仪器记录.xlsx',
            source_sheet_name: '动力学',
            source_version: 1,
            row_count: 2,
            field_count: 1,
            fields: [{
              field_id: 'field:x',
              name: 'Time_s',
              logical_type: 'numeric',
              physical_type: 'float64',
              unit: { source_text: 's', canonical_unit: null, dimensionality: 'opaque', kind: 'opaque', registry_version: 'units.v1' },
            }],
            sample_rows: [[1], [2]],
            quality: {},
            source_coordinate_kinds: ['excel'],
          }],
        },
        { kind: 'failed', source_file_name: '损坏.csv', error: { message: '无法解析' } },
      ],
    }

    expect(readDatasets(value)[0]).toMatchObject({
      datasetId: 'source:opaque',
      displayName: '仪器记录.xlsx > 动力学',
      sourceFileName: '仪器记录.xlsx',
      sourceSheetName: '动力学',
      sampleRows: [[1], [2]],
      fields: [expect.objectContaining({ unit: 's' })],
    })
    expect(readImportSummary(value)).toEqual({
      fileCount: 2,
      committedCount: 1,
      attentionCount: 0,
      failedCount: 1,
      committedFiles: ['仪器记录.xlsx'],
      attentionFiles: [],
      failedFiles: ['损坏.csv'],
      attentionDetails: [],
      failedDetails: ['损坏.csv：无法解析'],
    })
  })

  it('keeps text data blocks distinct and exposes preserved instrument metadata', () => {
    const datasets = readDatasets({
      datasets: [{
        source_dataset_id: 'source:block-two',
        source_file_name: 'instrument.txt',
        source_block: 'Sweep 2',
        source_version: 1,
        row_count: 2,
        field_count: 2,
        fields: [
          { field_id: 'field:x', name: 'x', logical_type: 'numeric', physical_type: 'float64', unit: null },
          { field_id: 'field:y', name: 'y', logical_type: 'numeric', physical_type: 'float64', unit: null },
        ],
        instrument_metadata: { Instrument: 'Spectrometer', Operator: 'Test' },
        quality: {},
        source_coordinate_kinds: ['text'],
      }],
    })

    expect(datasets[0]).toMatchObject({
      displayName: 'instrument.txt > Sweep 2',
      sourceBlock: 'Sweep 2',
      instrumentMetadata: { Instrument: 'Spectrometer', Operator: 'Test' },
    })
  })

  it('adds a stable identity suffix when source labels collide', () => {
    const fields = [
      { field_id: 'field:x', name: 'x', logical_type: 'numeric', physical_type: 'float64', unit: null },
    ]
    const datasets = readDatasets({
      datasets: [
        { source_dataset_id: 'source:directory-one-12345678', source_file_name: 'sample.xlsx', source_sheet_name: 'Data', source_version: 1, fields },
        { source_dataset_id: 'source:directory-two-87654321', source_file_name: 'sample.xlsx', source_sheet_name: 'Data', source_version: 1, fields },
      ],
    })

    expect(datasets.map((dataset) => dataset.displayName)).toEqual([
      'sample.xlsx > Data · 12345678',
      'sample.xlsx > Data · 87654321',
    ])
  })

  it('disambiguates same-name sources after separate imports are merged', () => {
    const response = (datasetId: string): JsonValue => ({
      datasets: [{
        source_dataset_id: datasetId,
        source_file_name: 'sample.xlsx',
        source_sheet_name: 'Data',
        source_version: 1,
        fields: [{ field_id: 'field:x', name: 'x' }],
      }],
    })
    const first = readDatasets(response('source:directory-one-12345678'))
    const second = readDatasets(response('source:directory-two-87654321'))

    expect(disambiguateDatasetDisplayNames([...first, ...second]).map((dataset) => dataset.displayName)).toEqual([
      'sample.xlsx > Data · 12345678',
      'sample.xlsx > Data · 87654321',
    ])
  })

  it('accounts for every selected import file and keeps clarification details actionable', () => {
    expect(readImportSummary({
      selected_files: ['清晰.csv', '待确认.txt', '无回执.dat'],
      imports: [
        { kind: 'committed', source_file_name: '清晰.csv', datasets: [] },
        {
          kind: 'clarification',
          source_file_name: '待确认.txt',
          question: '请选择分隔符。',
          options: [{ value: ',', label: ',' }, { value: ';', label: ';' }],
        },
      ],
    })).toEqual({
      fileCount: 3,
      committedCount: 1,
      attentionCount: 1,
      failedCount: 1,
      committedFiles: ['清晰.csv'],
      attentionFiles: ['待确认.txt'],
      failedFiles: ['无回执.dat'],
      attentionDetails: ['待确认.txt：请选择分隔符。'],
      failedDetails: ['无回执.dat：未返回处理结果，请重试。'],
    })
  })

  it('reads semantic objects, public actions, and capabilities from PlotDocument', () => {
    const plot = readPlot({
      project_version: 7,
      preview: {
        resourceId: 'resource:preview',
        kind: 'preview',
        url: 'plotagent-resource://preview/plot-test.png',
      },
      document: {
        plot_id: 'plot:test',
        plot_version: 3,
        profile_id: 'K02',
        data: {
          kind: 'source', dataset_id: 'source:test', version: 1,
          content_hash: 'a'.repeat(64),
        },
        bindings: [
          { role: 'x', field_id: 'field:x' },
          { role: 'y', field_id: 'field:y' },
        ],
      },
      profile: {
        profile_id: 'K02',
        objects: [
          { object_alias: 'x_axis', object_kind: 'axis', object_key: 'x' },
          { object_alias: 'y_axis', object_kind: 'axis', object_key: 'y' },
          { object_alias: 'series_1', object_kind: 'series', object_key: 'primary' },
          { object_alias: 'legend', object_kind: 'legend', object_key: 'main' },
        ],
        capabilities: [
          { operation: 'set_title', parameters: ['text'] },
          { operation: 'set_axis', parameters: ['label', 'scale', 'bounds', 'reverse'] },
          { operation: 'set_series_style', parameters: [
            'line_stroke_color', 'line_width_pt', 'line_style',
            'marker_shape', 'marker_size_pt',
          ] },
          { operation: 'set_legend', parameters: ['visible', 'anchor'] },
          { operation: 'add_annotation', parameters: ['text'] },
        ],
      },
      actions: [
        { operation: 'set_title', target: 'plot:test', text: 'Persisted title' },
        { operation: 'set_axis', target: 'axis:test.x', label: 'Time' },
        { operation: 'set_axis', target: 'axis:test.y', label: 'Signal', scale: 'log10', minimum: 0.1, maximum: 100 },
        { operation: 'set_axis', target: 'axis:test.y', tick_labels_visible: false, minor_ticks_visible: false, tick_direction: 'inout', axis_line_visible: false },
        { operation: 'set_series_style', target: 'series:test.primary', line_stroke_color: '#123456', line_width_pt: 1.5, marker_size_pt: 7, line_style: 'dash', marker_shape: 'diamond' },
        { operation: 'set_series_style', target: 'series:test.primary', visible: false },
        { operation: 'set_legend', target: 'legend:test.main', visible: false },
        { operation: 'set_legend', target: 'legend:test.main', anchor: 'right' },
        { operation: 'add_annotation', target: 'plot:test', annotation_id: 'annotation:test', text: 'Peak', x: 2, y: 5 },
      ],
    })

    expect(plot).toMatchObject({
      plotId: 'plot:test',
      plotVersion: 3,
      chartId: 'K02',
      engineData: {
        kind: 'source', dataset_id: 'source:test', version: 1,
        content_hash: 'a'.repeat(64),
      },
      engineBindings: [
        { role: 'x', field_id: 'field:x' },
        { role: 'y', field_id: 'field:y' },
      ],
      plotTitle: 'Persisted title',
      fontSizePt: 9,
      projectVersion: 7,
      seriesIds: ['series:test.primary'],
      axisIds: { x: 'axis:test.x', y: 'axis:test.y' },
      axisStates: {
        x: { axisId: 'axis:test.x', label: 'Time', scale: 'linear', reverse: false },
        y: { axisId: 'axis:test.y', label: 'Signal', scale: 'log10', minimum: 0.1, maximum: 100, reverse: false, tickLabelsVisible: false, minorTicksVisible: false, tickDirection: 'inout', axisLineVisible: false },
      },
      canvasSizeMm: { width: 183, height: 120 },
      annotations: [{ annotationId: 'annotation:test', kind: 'text', text: 'Peak', x: 2, y: 5 }],
      style: { legendVisible: false, legendPlacement: 'right' },
    })
    expect(plot?.seriesStyles[0]?.style).toEqual({
      visible: false,
      lineStrokeColor: '#123456',
      lineWidthPt: 1.5,
      markerSizePt: 7,
      lineStyle: 'dash',
      markerShape: 'diamond',
    })
    expect(plot?.engineCapabilities?.set_axis).toEqual(['label', 'scale', 'bounds', 'reverse'])
    expect(plot?.preview?.url).toBe('plotagent-resource://preview/plot-test.png')
  })

  it('preserves the Core commit order when reading the latest plot per object', () => {
    const plots = readPlots({
      project_version: 9,
      plots: [
        {
          document: {
            plot_id: 'plot:zeta', plot_version: 4, profile_id: 'K01',
            data: { kind: 'source', dataset_id: 'source:zeta', version: 1, content_hash: 'b'.repeat(64) },
            bindings: [{ role: 'x', field_id: 'field:zeta.x' }, { role: 'y', field_id: 'field:zeta.y' }],
          },
          profile: { profile_id: 'K01', objects: [], capabilities: [] },
          actions: [],
        },
        {
          document: {
            plot_id: 'plot:alpha', plot_version: 2, profile_id: 'K02',
            data: { kind: 'source', dataset_id: 'source:alpha', version: 1, content_hash: 'c'.repeat(64) },
            bindings: [{ role: 'x', field_id: 'field:alpha.x' }, { role: 'y', field_id: 'field:alpha.y' }],
          },
          profile: { profile_id: 'K02', objects: [], capabilities: [] },
          actions: [],
        },
      ],
    })

    expect(plots.map((plot) => `${plot.plotId}@${plot.plotVersion}`)).toEqual([
      'plot:zeta@4',
      'plot:alpha@2',
    ])
    expect(plots.at(-1)?.chartId).toBe('K02')
  })

  it('reads explicit output plots without inferring them from target strings', () => {
    const plan = readWorkflowPlan({
      plan: {
        plan_id: 'plan:set-y-log',
        items: [{
          item_id: 'item:set-y-log',
          task_kind: 'edit',
          profile_id: 'K01',
          sources: [],
          bindings: [],
          visual_actions: [{ operation: 'set_axis', target_alias: 'y_axis', scale: 'log10' }],
        }],
      },
      state: 'succeeded',
      item_progress: [{
        item_id: 'item:set-y-log',
        state: 'succeeded',
        attempt_count: 1,
        output_plot_id: 'plot:agent.line_temp_response.1',
        output_plot_version: 5,
      }],
    })

    expect(plan?.steps[0]?.outputPlot).toEqual({
      plotId: 'plot:agent.line_temp_response.1',
      plotVersion: 5,
    })
    expect(plan?.steps[0]).toMatchObject({
      taskKind: 'edit',
      profileId: 'K01',
      title: '修改 K01',
      detail: '1 项视觉修改',
      bindings: [],
      changes: ['坐标轴（y_axis）：刻度=log10'],
    })
  })

  it('surfaces ordered filter and sort operations in the confirmation plan', () => {
    const plan = readWorkflowPlan({
      plan: {
        plan_id: 'plan:data-ops',
        items: [{
          item_id: 'item:data-ops',
          task_kind: 'update_data',
          profile_id: 'K03',
          sources: [{ source_alias: 'source_1', source_dataset_id: 'dataset:temperature' }],
          resolved_fields: [
            { field_alias: 'field_temperature', name: '温度' },
            { field_alias: 'field_response', name: 'Response_mV' },
          ],
          data_operations: [
            {
              operation: 'filter_rows',
              source_alias: 'source_1',
              predicates: [{ field_alias: 'field_temperature', operator: 'greater_or_equal', value: 30 }],
              combine: 'all',
            },
            {
              operation: 'sort_rows',
              source_alias: 'source_1',
              keys: [{ field_alias: 'field_response', direction: 'descending', missing: 'last' }],
            },
          ],
          bindings: [
            { role: 'x', source_alias: 'source_1', field_id: 'field:temperature' },
            { role: 'y', source_alias: 'source_1', field_id: 'field:response' },
          ],
          visual_actions: [],
        }],
      },
      state: 'awaiting_confirmation',
      item_progress: [{ item_id: 'item:data-ops', state: 'pending', attempt_count: 0 }],
    })

    expect(plan?.steps[0]).toMatchObject({
      detail: '2 个字段角色 · 2 项数据处理',
      dataOperations: ['筛选：温度 ≥ 30', '排序：Response_mV 降序'],
    })
  })

  it('preserves readable names for fields derived inside a workflow', () => {
    const plan = readWorkflowPlan({
      plan: {
        plan_id: 'plan:derived-binding',
        items: [{
          item_id: 'item:derived-binding',
          task_kind: 'create',
          profile_id: 'K01',
          sources: [{ source_alias: 'source_1', source_dataset_id: 'dataset:sensor' }],
          resolved_fields: [{
            field_alias: 'signal_v',
            field_id: 'field:workflow_internal_signal_v',
            name: 'Signal (V)',
          }],
          data_operations: [],
          bindings: [{
            role: 'y',
            source_alias: 'source_1',
            field_id: 'field:workflow_internal_signal_v',
          }],
          visual_actions: [],
        }],
      },
      state: 'awaiting_confirmation',
      item_progress: [{ item_id: 'item:derived-binding', state: 'pending', attempt_count: 0 }],
    })

    expect(plan?.steps[0]?.bindings).toEqual([{
      role: 'y',
      fieldId: 'field:workflow_internal_signal_v',
      sourceDatasetId: 'dataset:sensor',
      fieldName: 'Signal (V)',
    }])
  })

  it('reads compiler-owned raw-field evidence for aligned multi-source bindings', () => {
    const plan = readWorkflowPlan({
      plan: {
        plan_id: 'plan:aligned-evidence',
        items: [{
          item_id: 'item:aligned-evidence',
          task_kind: 'create',
          profile_id: 'X38',
          sources: [
            { source_alias: 'data_1', source_dataset_id: 'source:first' },
            { source_alias: 'data_2', source_dataset_id: 'source:second' },
          ],
          resolved_fields: [
            { field_alias: 'x_1', field_id: 'field:first.x', name: 'Angle' },
            { field_alias: 'y_1', field_id: 'field:first.y', name: 'PSD' },
            { field_alias: 'x_2', field_id: 'field:second.x', name: 'Angle' },
            { field_alias: 'y_2', field_id: 'field:second.y', name: 'PSD' },
            { field_alias: 'aligned_x', field_id: 'field:workflow.x', name: 'Angle' },
            { field_alias: 'series_a', field_id: 'field:workflow.a', name: 'A' },
            { field_alias: 'series_b', field_id: 'field:workflow.b', name: 'B' },
          ],
          data_operations: [{ operation: 'align_sources_on_x' }],
          bindings: [
            { role: 'x', source_alias: 'data_1', field_id: 'field:workflow.x' },
            { role: 'series_1', source_alias: 'data_1', field_id: 'field:workflow.a' },
            { role: 'series_2', source_alias: 'data_1', field_id: 'field:workflow.b' },
          ],
          binding_evidence: [
            { role: 'x', source_alias: 'data_1', field_id: 'field:first.x' },
            { role: 'x', source_alias: 'data_2', field_id: 'field:second.x' },
            { role: 'series_1', source_alias: 'data_1', field_id: 'field:first.y' },
            { role: 'series_2', source_alias: 'data_2', field_id: 'field:second.y' },
          ],
          visual_actions: [],
        }],
      },
      state: 'awaiting_confirmation',
      item_progress: [{
        item_id: 'item:aligned-evidence',
        state: 'pending',
        attempt_count: 0,
      }],
    })

    expect(plan?.steps[0]?.sourceFieldRoles).toEqual([
      { role: 'x', fieldId: 'field:first.x', sourceDatasetId: 'source:first' },
      { role: 'x', fieldId: 'field:second.x', sourceDatasetId: 'source:second' },
      { role: 'series_1', fieldId: 'field:first.y', sourceDatasetId: 'source:first' },
      { role: 'series_2', fieldId: 'field:second.y', sourceDatasetId: 'source:second' },
    ])
  })

  it('uses per-item progress for isolated batch failures and retry attempts', () => {
    const plan = readWorkflowPlan({
      plan: {
        plan_id: 'plan:isolated',
        items: ['a-create', 'a-scale', 'b-create'].map((id) => ({
          item_id: `item:${id}`,
          task_kind: id === 'a-scale' ? 'edit' : 'create',
          profile_id: 'K01',
          sources: id === 'a-scale' ? [] : [{ source_dataset_id: `source:${id}` }],
          bindings: id === 'a-scale' ? [] : [{ role: 'x', field_id: 'field:x' }],
          visual_actions: id === 'a-scale'
            ? [{ operation: 'set_axis', target_alias: 'y_axis', scale: 'log10' }]
            : [],
        })),
      },
      state: 'partially_succeeded',
      item_progress: [
        { item_id: 'item:a-create', state: 'succeeded', attempt_count: 1 },
        {
          item_id: 'item:a-scale',
          state: 'failed',
          attempt_count: 2,
          error_code: 'PROJECT_VERSION_CONFLICT',
          error_message: '项目版本已经变化，请重新执行。',
          error_retryable: true,
          last_error: {
            code: 'ORIGIN_BUSY',
            category: 'deterministic_technical',
            message: 'Origin 暂时忙碌。',
            retryable: true,
            requires_user: false,
            side_effect_state: 'known_none',
          },
        },
        { item_id: 'item:b-create', state: 'succeeded', attempt_count: 1 },
      ],
    })

    expect(plan?.steps.map((step) => step.state)).toEqual(['succeeded', 'failed', 'succeeded'])
    expect(plan?.steps[1]?.attemptCount).toBe(2)
    expect(plan?.steps[1]?.failure).toEqual({
      code: 'PROJECT_VERSION_CONFLICT',
      message: '项目版本已经变化，请重新执行。',
      retryable: true,
      category: 'deterministic_technical',
      sideEffectState: 'known_none',
    })
    expect(plan?.completedCount).toBe(2)
    expect(plan?.resumable).toBe(false)
  })

  it('does not offer resume for a deterministic data failure', () => {
    const plan = readWorkflowPlan({
      plan: {
        plan_id: 'plan:nonretryable',
        items: [{
          item_id: 'item:scale',
          task_kind: 'edit',
          profile_id: 'K01',
          sources: [],
          bindings: [],
          visual_actions: [{ operation: 'set_axis', target_alias: 'y_axis', scale: 'log10' }],
        }],
      },
      state: 'failed',
      item_progress: [{
        item_id: 'item:scale',
        state: 'failed',
        attempt_count: 1,
        error_code: 'LOG_SCALE_NON_POSITIVE',
        error_message: 'Log10 轴包含 0 或负值；任务未执行，项目没有发生变化。',
        error_retryable: false,
      }],
    })

    expect(plan?.steps[0]?.failure?.message).toContain('0 或负值')
    expect(plan?.resumable).toBe(false)
  })

  it('does not offer unchanged retry for a persisted plan-revision failure', () => {
    const plan = readWorkflowPlan({
      plan: {
        plan_id: 'plan:missing-combine',
        items: [{
          item_id: 'item:missing-combine',
          task_kind: 'create',
          profile_id: 'X38',
          sources: [
            { source_alias: 'data_1', source_dataset_id: 'source:one' },
            { source_alias: 'data_2', source_dataset_id: 'source:two' },
          ],
          bindings: [],
          visual_actions: [],
        }],
      },
      state: 'partial',
      item_progress: [{
        item_id: 'item:missing-combine',
        state: 'repairable_failed',
        attempt_count: 1,
        last_error: {
          code: 'WORKFLOW_SOURCES_NOT_COMBINED',
          category: 'deterministic_technical',
          message: '多来源尚未合并。',
          retryable: true,
          requires_user: false,
          side_effect_state: 'known_none',
        },
      }],
    })

    expect(plan?.state).toBe('partially_succeeded')
    expect(plan?.resumable).toBe(false)
  })

  it('preserves the binding source when field ids repeat across datasets', () => {
    const plan = readWorkflowPlan({
      plan: {
        plan_id: 'plan:source-qualified-bindings',
        items: [{
          item_id: 'item:create',
          task_kind: 'create',
          profile_id: 'K03',
          sources: [{ source_alias: 'data_2', source_dataset_id: 'source:k03' }],
          bindings: [
            { role: 'x', source_alias: 'data_2', field_id: 'field:shared-x' },
            { role: 'y', source_alias: 'data_2', field_id: 'field:shared-y' },
          ],
          visual_actions: [],
        }],
      },
      state: 'awaiting_confirmation',
      item_progress: [{ item_id: 'item:create', state: 'pending', attempt_count: 0 }],
    })

    expect(plan?.steps[0]?.bindings).toEqual([
      { role: 'x', fieldId: 'field:shared-x', sourceDatasetId: 'source:k03' },
      { role: 'y', fieldId: 'field:shared-y', sourceDatasetId: 'source:k03' },
    ])
  })

  it('reads the durable Agent v2 plan and checkpoint as the same confirmation card', () => {
    const plan = readWorkflowPlan({
      task: {
        task_id: 'task:durable',
        task_version: 3,
        state: 'completed_verified',
        items: [{
          item_id: 'item:durable.1',
          state: 'succeeded',
          attempt_count: 1,
          output_plot_id: 'plot:durable.1',
          output_plot_version: 1,
        }],
      },
      plan: {
        plan_id: 'plan:durable',
        items: [{
          item_id: 'item:durable.1',
          task_kind: 'create',
          profile_id: 'K01',
          sources: [{ source_alias: 'data_1', source_dataset_id: 'source:durable' }],
          bindings: [
            { role: 'x', source_alias: 'data_1', field_id: 'field:time' },
            { role: 'y', source_alias: 'data_1', field_id: 'field:value' },
          ],
          visual_actions: [],
        }],
      },
      plan_hash: 'a'.repeat(64),
      confirmation_state: 'confirmed',
    })

    expect(plan).toMatchObject({
      planId: 'plan:durable',
      taskId: 'task:durable',
      taskVersion: 3,
      state: 'succeeded',
      confirmationState: 'confirmed',
      completedCount: 1,
    })
    expect(plan?.steps[0]).toMatchObject({
      state: 'succeeded',
      outputPlot: { plotId: 'plot:durable.1', plotVersion: 1 },
      sourceDatasetIds: ['source:durable'],
    })
  })

  it('reads the exact prepared schema, units, samples, and structured preview failure', () => {
    const plan = readWorkflowPlan({
      task: {
        task_id: 'task:prepared',
        task_version: 2,
        state: 'awaiting_confirmation',
        items: [
          { item_id: 'item:prepared.1', state: 'staged', attempt_count: 0 },
          { item_id: 'item:prepared.2', state: 'staged', attempt_count: 0 },
        ],
      },
      plan: {
        plan_id: 'plan:prepared',
        items: [
          {
            item_id: 'item:prepared.1',
            task_kind: 'create',
            profile_id: 'K03',
            sources: [{ source_alias: 'data_1', source_dataset_id: 'source:wide' }],
            bindings: [
              { role: 'x', source_alias: 'data_1', field_id: 'field:time' },
              { role: 'y', source_alias: 'data_1', field_id: 'field:value' },
            ],
            visual_actions: [],
          },
          {
            item_id: 'item:prepared.2',
            task_kind: 'create',
            profile_id: 'K03',
            sources: [{ source_alias: 'data_2', source_dataset_id: 'source:invalid' }],
            bindings: [],
            visual_actions: [],
          },
        ],
      },
      prepared_previews: [{
        item_id: 'item:prepared.1',
        sources: [{
          source_dataset_id: 'source:wide', source_version: 1,
          display_name: 'wide.xlsx > Data', row_count: 2,
        }],
        input_row_count: 2,
        input_field_count: 3,
        output_row_count: 4,
        output_field_count: 3,
        fields: [
          { field_id: 'field:time', name: 'Time', logical_type: 'numeric', unit_label: 's' },
          { field_id: 'field:series', name: 'Series', logical_type: 'categorical', unit_label: null },
          { field_id: 'field:value', name: 'Value', logical_type: 'numeric', unit_label: 'mV' },
        ],
        rows: [[1, 'A', 10], [1, 'B', 30], [2, 'A', 20]],
        content_hash: 'c'.repeat(64),
      }],
      prepared_preview_errors: [{
        item_id: 'item:prepared.2',
        code: 'WORKFLOW_NON_ISOMORPHIC',
        message: '整理后的字段仍不一致。',
      }],
      plan_hash: 'a'.repeat(64),
      confirmation_state: 'pending',
    })

    expect(plan?.steps[0]?.preparedPreview).toEqual({
      inputRowCount: 2,
      inputFieldCount: 3,
      outputRowCount: 4,
      outputFieldCount: 3,
      sources: [{
        datasetId: 'source:wide', sourceVersion: 1,
        displayName: 'wide.xlsx > Data', rowCount: 2,
      }],
      fields: [
        { fieldId: 'field:time', name: 'Time', logicalType: 'numeric', unit: 's' },
        { fieldId: 'field:series', name: 'Series', logicalType: 'categorical' },
        { fieldId: 'field:value', name: 'Value', logicalType: 'numeric', unit: 'mV' },
      ],
      rows: [[1, 'A', 10], [1, 'B', 30], [2, 'A', 20]],
      contentHash: 'c'.repeat(64),
    })
    expect(plan?.steps[1]?.preparedPreviewError).toEqual({
      code: 'WORKFLOW_NON_ISOMORPHIC',
      message: '整理后的字段仍不一致。',
    })
  })

  it('reads durable task progress, retained outputs, and safe diagnostics without inferring them from chat', () => {
    const tasks = readDurableTasks({
      durable_tasks: [{
        task_id: 'task:partial',
        task_version: 8,
        state: 'partial',
        project_revision: 12,
        active_activation_id: 'activation:partial-repair',
        updated_at: '2026-08-18T07:00:00Z',
        items: [
          {
            item_id: 'item:kept',
            state: 'succeeded',
            attempt_count: 1,
            output_plot_id: 'plot:kept',
            output_plot_version: 2,
          },
          {
            item_id: 'item:failed',
            state: 'repairable_failed',
            attempt_count: 2,
            last_error: {
              code: 'ORIGIN_BUSY',
              message: 'Origin is busy.',
              retryable: true,
              diagnostic_id: 'diag:safe-1',
            },
          },
        ],
      }],
    })

    expect(tasks).toEqual([{
      taskId: 'task:partial',
      taskVersion: 8,
      state: 'partial',
      projectRevision: 12,
      activeActivationId: 'activation:partial-repair',
      updatedAt: '2026-08-18T07:00:00Z',
      items: [
        {
          itemId: 'item:kept',
          state: 'succeeded',
          attemptCount: 1,
          outputPlot: { plotId: 'plot:kept', plotVersion: 2 },
        },
        {
          itemId: 'item:failed',
          state: 'repairable_failed',
          attemptCount: 2,
          failure: {
            code: 'ORIGIN_BUSY',
            message: 'Origin is busy.',
            retryable: true,
            diagnosticId: 'diag:safe-1',
          },
        },
      ],
    }])
  })

  it('never projects a terminal failed task as resumable even when its error was retryable', () => {
    const plan = readWorkflowPlan({
      task: {
        task_id: 'task:failed-terminal',
        task_version: 5,
        state: 'failed',
        items: [{
          item_id: 'item:failed-terminal.1',
          state: 'failed',
          attempt_count: 1,
          last_error: {
            code: 'ORIGIN_BUSY',
            category: 'deterministic_technical',
            message: 'Origin is busy.',
            retryable: true,
            requires_user: false,
            side_effect_state: 'known_none',
          },
        }],
      },
      plan: {
        plan_id: 'plan:failed-terminal',
        items: [{
          item_id: 'item:failed-terminal.1',
          task_kind: 'create',
          profile_id: 'K01',
          sources: [],
          bindings: [],
          visual_actions: [],
        }],
      },
      plan_hash: 'a'.repeat(64),
      confirmation_state: 'unavailable',
    })

    expect(plan).toMatchObject({ state: 'failed', resumable: false })
  })
})
