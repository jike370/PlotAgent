import { describe, expect, it } from 'vitest'

import type { JsonValue } from '../../../shared/desktop-contract'
import {
  disambiguateDatasetDisplayNames,
  readWorkflowPlan,
  readDataPreparationRecipes,
  readDataPreparationRun,
  readEngineCompatibility,
  readDatasets,
  readImportSummary,
  readPlot,
  readPlots,
} from './productState'

describe('product plot state', () => {
  it('reads saved data preparation recipes without plotting semantics', () => {
    expect(readDataPreparationRecipes({
      data_preparation_recipes: [{
        recipe_id: 'data-recipe:line',
        recipe_version: 2,
        display_name: '仪器表整理',
        scope: 'personal',
        match_contract: { source_formats: ['xlsx'], table_count: 3 },
      }],
    })).toEqual([{
      recipeId: 'data-recipe:line',
      recipeVersion: 2,
      displayName: '仪器表整理',
      scope: 'personal',
      sourceFormats: ['xlsx'],
      tableCount: 3,
    }])
  })

  it('reads a data preparation run and its local-cost metadata', () => {
    expect(readDataPreparationRun({
      run_id: 'data-run:one',
      state: 'committed',
      route: 'saved_recipe',
      selected_recipe_id: 'data-recipe:line',
      selected_recipe_version: 2,
      probe: { tables: [{ table_key: 'Sheet1' }] },
      local_duration_ms: 17,
    })).toEqual({
      runId: 'data-run:one',
      state: 'committed',
      route: 'saved_recipe',
      selectedRecipeId: 'data-recipe:line',
      selectedRecipeVersion: 2,
      tableCount: 1,
      localDurationMs: 17,
    })
  })

  it('reads only explicit profile compatibility statuses', () => {
    expect(readEngineCompatibility({
      compatibility: [
        { profile_id: 'K01', status: 'compatible' },
        { profile_id: 'K06', status: 'incompatible' },
        { profile_id: 'K07', status: 'unknown' },
      ],
    })).toEqual({ K01: 'compatible', K06: 'incompatible' })
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
        { operation: 'set_series_style', target: 'series:test.primary', line_stroke_color: '#123456', line_width_pt: 1.5, marker_size_pt: 7, line_style: 'dash', marker_shape: 'diamond' },
        { operation: 'set_legend', target: 'legend:test.main', visible: false, anchor: 'right' },
        { operation: 'add_annotation', target: 'plot:test', annotation_id: 'annotation:test', text: 'Peak', x: 2, y: 5 },
      ],
    })

    expect(plot).toMatchObject({
      plotId: 'plot:test',
      plotVersion: 3,
      chartId: 'K02',
      plotTitle: 'Persisted title',
      fontSizePt: 9,
      projectVersion: 7,
      seriesIds: ['series:test.primary'],
      axisIds: { x: 'axis:test.x', y: 'axis:test.y' },
      axisStates: {
        x: { axisId: 'axis:test.x', label: 'Time', scale: 'linear', reverse: false },
        y: { axisId: 'axis:test.y', label: 'Signal', scale: 'log10', minimum: 0.1, maximum: 100, reverse: false },
      },
      canvasSizeMm: { width: 183, height: 120 },
      annotations: [{ annotationId: 'annotation:test', kind: 'text', text: 'Peak', x: 2, y: 5 }],
      style: { legendVisible: false, legendPlacement: 'right' },
    })
    expect(plot?.seriesStyles[0]?.style).toEqual({
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
          document: { plot_id: 'plot:zeta', plot_version: 4, profile_id: 'K01' },
          profile: { profile_id: 'K01', objects: [], capabilities: [] },
          actions: [],
        },
        {
          document: { plot_id: 'plot:alpha', plot_version: 2, profile_id: 'K02' },
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
    })
    expect(plan?.completedCount).toBe(2)
    expect(plan?.resumable).toBe(true)
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
})
