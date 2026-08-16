// Generated from schemas/contracts-bundle.schema.json. Do not edit.

export const CONTRACT_SCHEMA_VERSION = "1.0" as const

export type AddAnnotation = {
  readonly expected_plot_version: number;
  readonly operation?: "add_annotation";
  readonly action_id: string;
  readonly target: string;
  readonly annotation_id: string;
  readonly text: string;
  readonly x: number;
  readonly y: number;
  readonly coordinate_system?: "data" | "axes" | "page";
  readonly font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly font_size_pt?: number | null;
  readonly font_weight?: "normal" | "bold" | null;
  readonly italic?: boolean | null;
  readonly color?: string | null;
  readonly rotation_deg?: number | null;
}

export type ApplyPlotOrderSpec = {
  readonly schema_version?: "1.0";
  readonly preparation_spec_id: string;
  readonly preparation_version: number;
  readonly input_refs: ReadonlyArray<SourceDatasetRef>;
  readonly field_mapping_ref: FieldMappingRef;
  readonly compiler_version: string;
  readonly kind?: "apply_plot_order";
  readonly field_id: string;
  readonly ordered_values: ReadonlyArray<string>;
}

export type BindFields = {
  readonly expected_plot_version: number;
  readonly operation?: "bind_fields";
  readonly action_id: string;
  readonly target: string;
  readonly data: EngineDataRef;
  readonly bindings: ReadonlyArray<FieldBinding>;
}

export type CalculateChartData = {
  readonly operation?: "calculate_chart_data";
  readonly calculation: "histogram_binning" | "tukey_box" | "violin_kde" | "summary_error" | "percent_stack" | "matrix_projection" | "confusion_count";
}

export type CalculationTable = {
  readonly field_ids: ReadonlyArray<string>;
  readonly rows: ReadonlyArray<ReadonlyArray<string | boolean | number | null>>;
}

export type CompiledTaskItem = {
  readonly task_kind: "create" | "edit";
  readonly item_id: string;
  readonly plot_alias: string;
  readonly plot_id: string;
  readonly profile_id: string;
  readonly target_plot_id?: string | null;
  readonly target_plot_version?: number | null;
  readonly sources?: ReadonlyArray<WorkflowSource>;
  readonly resolved_fields?: ReadonlyArray<ResolvedWorkflowField>;
  readonly data_operations: ReadonlyArray<SelectFields | FilterRows | SortRows | ReshapeLongToWide | ReshapeWideToLong | ConcatenateSources | CalculateChartData>;
  readonly bindings?: ReadonlyArray<ResolvedFieldBinding>;
  readonly visual_actions: ReadonlyArray<DraftSetTitle | DraftSetAxis | DraftSetSeriesStyle | DraftSetLegend | DraftSetColorMap | DraftSetErrorStyle | DraftSetDataLabels | DraftSetChartParameter | DraftAddAnnotation>;
  readonly depends_on?: ReadonlyArray<string>;
  readonly idempotency_key: string;
}

export type ConcatenateSources = {
  readonly operation?: "concatenate_sources";
  readonly source_aliases: ReadonlyArray<string>;
  readonly source_label_field?: string;
}

export type ConfusionCountResult = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly result_version: number;
  readonly spec_ref: PlotCalculationSpecRef;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly input_hash: string;
  readonly output_hash: string;
  readonly output_data_ref: ContentTableRef;
  readonly output_table: CalculationTable;
  readonly total_row_count: number;
  readonly included_row_count: number;
  readonly excluded_row_count: number;
  readonly included_row_ids: ReadonlyArray<string>;
  readonly exclusions?: ReadonlyArray<RowExclusion>;
  readonly nonfinite_counts?: NonFiniteCounts;
  readonly fixed_seed?: number | null;
  readonly warnings?: ReadonlyArray<WarningRecord>;
  readonly producer_build_hash: string;
  readonly kind?: "confusion_count";
  readonly algorithm_id?: "fixed_confusion_count";
  readonly normalization: "count" | "true_class" | "predicted_class";
  readonly category_count: number;
  readonly category_order: ReadonlyArray<string>;
}

export type ConfusionCountSpec = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly calculation_version: number;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly log10_fields?: ReadonlyArray<string>;
  readonly fixed_seed?: number | null;
  readonly kind?: "confusion_count";
  readonly algorithm_id?: "fixed_confusion_count";
  readonly actual_field: string;
  readonly predicted_field: string;
  readonly count_field?: string | null;
  readonly normalization?: "count" | "true_class" | "predicted_class";
  readonly category_order?: ReadonlyArray<string>;
}

export type ContentTableRef = {
  readonly object_hash: string;
  readonly row_count: number;
  readonly field_ids: ReadonlyArray<string>;
}

export type CreatePlot = {
  readonly operation?: "create_plot";
  readonly action_id: string;
  readonly plot_id: string;
  readonly profile_id: string;
  readonly data: EngineDataRef;
  readonly bindings: ReadonlyArray<FieldBinding>;
}

export type DataQualitySummary = {
  readonly total_rows: number;
  readonly valid_rows: number;
  readonly missing_values: number;
  readonly nan_values: number;
  readonly positive_inf_values: number;
  readonly negative_inf_values: number;
  readonly unparseable_values: number;
  readonly warnings?: ReadonlyArray<WarningRecord>;
}

export type DraftAddAnnotation = {
  readonly operation?: "add_annotation";
  readonly target_alias?: string;
  readonly annotation_alias: string;
  readonly text: string;
  readonly x: number;
  readonly y: number;
  readonly coordinate_system?: "data" | "axes" | "page";
  readonly font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly font_size_pt?: number | null;
  readonly font_weight?: "normal" | "bold" | null;
  readonly italic?: boolean | null;
  readonly color?: string | null;
  readonly rotation_deg?: number | null;
}

export type DraftFieldBinding = {
  readonly role: string;
  readonly source_alias: string;
  readonly field_alias: string;
}

export type DraftSetAxis = {
  readonly operation?: "set_axis";
  readonly target_alias: string;
  readonly label?: string | null;
  readonly scale?: "linear" | "log10" | "datetime" | "categorical" | null;
  readonly minimum?: number | null;
  readonly maximum?: number | null;
  readonly reverse?: boolean | null;
  readonly title_font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly title_font_size_pt?: number | null;
  readonly title_font_weight?: "normal" | "bold" | null;
  readonly title_italic?: boolean | null;
  readonly title_color?: string | null;
  readonly major_tick_step?: number | null;
  readonly minor_tick_count?: number | null;
  readonly tick_format?: "auto" | "decimal" | "scientific" | "percent" | "date" | "time" | null;
  readonly tick_rotation_deg?: number | null;
  readonly tick_font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly tick_font_size_pt?: number | null;
  readonly tick_color?: string | null;
  readonly axis_line_color?: string | null;
  readonly axis_line_width_pt?: number | null;
  readonly major_grid_visible?: boolean | null;
  readonly minor_grid_visible?: boolean | null;
  readonly grid_color?: string | null;
  readonly grid_line_width_pt?: number | null;
  readonly grid_line_style?: "solid" | "dash" | "dot" | "dash_dot" | "none" | null;
}

export type DraftSetChartParameter = {
  readonly operation?: "set_chart_parameter";
  readonly target_alias?: string;
  readonly parameter: string;
  readonly value: string | number | boolean;
}

export type DraftSetColorMap = {
  readonly operation?: "set_colormap";
  readonly target_alias: string;
  readonly palette?: "viridis" | "plasma" | "inferno" | "magma" | "cividis" | "turbo" | "blue_orange" | "red_white_blue" | "blue_white_red" | "gray_scale" | "fire" | "rainbow_modified" | "cool_warm" | "spectral" | "terrain" | "ocean" | null;
  readonly reverse?: boolean | null;
  readonly minimum?: number | null;
  readonly maximum?: number | null;
  readonly midpoint?: number | null;
  readonly mode?: "continuous" | "discrete" | null;
  readonly levels?: number | null;
  readonly missing_color?: string | null;
  readonly colorbar_visible?: boolean | null;
  readonly colorbar_anchor?: "right" | "bottom" | null;
  readonly colorbar_title?: string | null;
  readonly colorbar_tick_format?: "auto" | "decimal" | "scientific" | "percent" | null;
}

export type DraftSetDataLabels = {
  readonly operation?: "set_data_labels";
  readonly target_alias: string;
  readonly visible?: boolean | null;
  readonly value_format?: "auto" | "decimal" | "scientific" | "percent" | null;
  readonly prefix?: string | null;
  readonly suffix?: string | null;
  readonly position?: "auto" | "above" | "below" | "left" | "right" | "center" | null;
  readonly rotation_deg?: number | null;
  readonly font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly font_size_pt?: number | null;
  readonly font_weight?: "normal" | "bold" | null;
  readonly font_color?: string | null;
}

export type DraftSetErrorStyle = {
  readonly operation?: "set_error_style";
  readonly target_alias: string;
  readonly bar_color?: string | null;
  readonly bar_width_pt?: number | null;
  readonly cap_size_pt?: number | null;
  readonly bar_opacity?: number | null;
  readonly band_fill_color?: string | null;
  readonly band_fill_opacity?: number | null;
  readonly band_stroke_color?: string | null;
  readonly band_stroke_width_pt?: number | null;
}

export type DraftSetLegend = {
  readonly operation?: "set_legend";
  readonly target_alias?: string;
  readonly visible?: boolean | null;
  readonly anchor?: "inside" | "inside_top_left" | "inside_top_right" | "inside_bottom_left" | "inside_bottom_right" | "right" | "bottom" | "none" | null;
  readonly columns?: number | null;
  readonly title?: string | null;
  readonly font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly font_size_pt?: number | null;
  readonly font_color?: string | null;
  readonly frame_visible?: boolean | null;
  readonly frame_color?: string | null;
  readonly frame_width_pt?: number | null;
}

export type DraftSetSeriesStyle = {
  readonly operation?: "set_series_style";
  readonly target_alias: string;
  readonly line_stroke_color?: string | null;
  readonly line_width_pt?: number | null;
  readonly line_style?: "solid" | "dash" | "dot" | "dash_dot" | "none" | null;
  readonly line_opacity?: number | null;
  readonly marker_shape?: "circle" | "square" | "triangle_up" | "triangle_down" | "triangle_left" | "triangle_right" | "diamond" | "plus" | "cross" | "hexagon" | "star" | "pentagon" | "none" | null;
  readonly marker_size_pt?: number | null;
  readonly marker_interior?: "solid" | "open" | "hollow" | null;
  readonly marker_fill_color?: string | null;
  readonly marker_stroke_color?: string | null;
  readonly marker_stroke_width_pt?: number | null;
  readonly marker_opacity?: number | null;
  readonly fill_color?: string | null;
  readonly fill_opacity?: number | null;
  readonly fill_stroke_color?: string | null;
  readonly fill_stroke_width_pt?: number | null;
  readonly fill_stroke_style?: "solid" | "dash" | "dot" | "dash_dot" | "none" | null;
}

export type DraftSetTitle = {
  readonly operation?: "set_title";
  readonly target_alias?: string;
  readonly text?: string | null;
  readonly font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly font_size_pt?: number | null;
  readonly font_weight?: "normal" | "bold" | null;
  readonly italic?: boolean | null;
  readonly color?: string | null;
}

export type ECDFResult = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly result_version: number;
  readonly spec_ref: PlotCalculationSpecRef;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly input_hash: string;
  readonly output_hash: string;
  readonly output_data_ref: ContentTableRef;
  readonly output_table: CalculationTable;
  readonly total_row_count: number;
  readonly included_row_count: number;
  readonly excluded_row_count: number;
  readonly included_row_ids: ReadonlyArray<string>;
  readonly exclusions?: ReadonlyArray<RowExclusion>;
  readonly nonfinite_counts?: NonFiniteCounts;
  readonly fixed_seed?: number | null;
  readonly warnings?: ReadonlyArray<WarningRecord>;
  readonly producer_build_hash: string;
  readonly kind?: "ecdf";
  readonly algorithm_id?: "right_continuous_empirical_cdf";
  readonly mode: "ecdf" | "ccdf";
}

export type ECDFSpec = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly calculation_version: number;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly log10_fields?: ReadonlyArray<string>;
  readonly fixed_seed?: number | null;
  readonly kind?: "ecdf";
  readonly algorithm_id?: "right_continuous_empirical_cdf";
  readonly value_field: string;
  readonly mode?: "ecdf" | "ccdf";
}

export type EngineArtifact = {
  readonly backend: "matplotlib" | "origin";
  readonly format: "png" | "svg" | "opju";
  readonly artifact_hash: string;
  readonly artifact_size: number;
}

export type EngineCapability = {
  readonly operation: "create_plot" | "bind_fields" | "set_title" | "set_axis" | "set_series_style" | "set_legend" | "set_colormap" | "set_error_style" | "set_data_labels" | "set_chart_parameter" | "add_annotation" | "export_plot";
  readonly parameters?: ReadonlyArray<string>;
}

export type EngineColumn = {
  readonly field: EngineField;
  readonly values: ReadonlyArray<boolean | number | string | null>;
}

export type EngineDataRef = {
  readonly kind: "source" | "prepared" | "calculated";
  readonly dataset_id: string;
  readonly version: number;
  readonly content_hash: string;
}

export type EngineDataView = {
  readonly data: EngineDataRef;
  readonly row_ids: ReadonlyArray<string>;
  readonly columns: ReadonlyArray<EngineColumn>;
}

export type EngineField = {
  readonly field_id: string;
  readonly name: string;
  readonly logical_type: "numeric" | "categorical" | "datetime" | "boolean" | "text";
  readonly unit_label?: string | null;
}

export type EngineObjectRef = {
  readonly semantic_id: string;
  readonly backend: "matplotlib" | "origin";
  readonly object_kind: string;
  readonly native_ref: string;
}

export type EngineObjectTemplate = {
  readonly object_alias: string;
  readonly object_kind: "axis" | "series" | "legend" | "panel";
  readonly object_key: string;
}

export type EngineProfile = {
  readonly profile_id: string;
  readonly display_name: string;
  readonly required_roles: ReadonlyArray<string>;
  readonly optional_roles?: ReadonlyArray<string>;
  readonly repeatable_role_prefixes?: ReadonlyArray<string>;
  readonly objects?: ReadonlyArray<EngineObjectTemplate>;
  readonly repeatable_objects?: ReadonlyArray<EngineRepeatableObjectTemplate>;
  readonly capabilities: ReadonlyArray<EngineCapability>;
}

export type EngineReadback = {
  readonly document: PlotDocumentRef;
  readonly backend: "matplotlib" | "origin";
  readonly objects: ReadonlyArray<EngineObjectRef>;
  readonly data_hash: string;
  readonly style_hash: string;
}

export type EngineRepeatableObjectTemplate = {
  readonly object_alias_prefix: string;
  readonly object_kind: "series" | "panel";
  readonly object_key_prefix: string;
}

export type ErrorDefinition = {
  readonly code: string;
  readonly owner: "W0_CONTRACTS" | "W2_DATA" | "W3_CALCULATIONS" | "W4_RENDERING" | "W5_WORKFLOW" | "W6_ORIGIN" | "W7_AGENT";
  readonly retryable: boolean;
  readonly default_severity: "info" | "warning" | "blocked";
  readonly description: string;
}

export type ErrorRegistry = {
  readonly schema_version?: "1.0";
  readonly errors: ReadonlyArray<ErrorDefinition>;
}

export type ErrorResponse = {
  readonly schema_version?: "1.0";
  readonly code: string;
  readonly severity: "info" | "warning" | "blocked";
  readonly retryable: boolean;
  readonly message: string;
}

export type ExcelSourceCoordinate = {
  readonly kind?: "excel";
  readonly workbook_hash: string;
  readonly sheet_name: string;
  readonly cell_range: string;
  readonly source_row_id: string;
}

export type ExportPlot = {
  readonly expected_plot_version: number;
  readonly operation?: "export_plot";
  readonly action_id: string;
  readonly target: string;
  readonly format: "png" | "svg" | "opju";
  readonly output_name: string;
}

export type FieldBinding = {
  readonly role: string;
  readonly field_id: string;
}

export type FieldMapping = {
  readonly schema_version?: "1.0";
  readonly field_mapping_id: string;
  readonly mapping_version: number;
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "S34" | "S61" | "X02" | "X03" | "X05" | "X09" | "X13" | "X23" | "X24" | "X35" | "X36" | "X38" | "X39" | "X40";
  readonly source_dataset_refs: ReadonlyArray<SourceDatasetRef>;
  readonly bindings: ReadonlyArray<FieldRoleBinding>;
  readonly content_hash: string;
}

export type FieldMappingRef = {
  readonly field_mapping_id: string;
  readonly mapping_version: number;
  readonly content_hash: string;
}

export type FieldRoleBinding = {
  readonly role: string;
  readonly field: FieldSnapshot;
}

export type FieldSnapshot = {
  readonly field_id: string;
  readonly name: string;
  readonly logical_type: "numeric" | "categorical" | "datetime" | "boolean" | "text";
  readonly unit: UnitSpec;
  readonly source_dataset_ref: SourceDatasetRef;
}

export type FilterPredicate = {
  readonly field_alias: string;
  readonly operator: "equal" | "not_equal" | "less_than" | "less_or_equal" | "greater_than" | "greater_or_equal" | "is_missing" | "is_not_missing" | "in_values";
  readonly value?: boolean | number | string | ReadonlyArray<boolean | number | string | null> | null;
}

export type FilterRows = {
  readonly operation?: "filter_rows";
  readonly source_alias: string;
  readonly predicates: ReadonlyArray<FilterPredicate>;
  readonly combine?: "all" | "any";
}

export type FilterRowsSpec = {
  readonly schema_version?: "1.0";
  readonly preparation_spec_id: string;
  readonly preparation_version: number;
  readonly input_refs: ReadonlyArray<SourceDatasetRef>;
  readonly field_mapping_ref: FieldMappingRef;
  readonly compiler_version: string;
  readonly kind?: "filter_rows";
  readonly field_ids: ReadonlyArray<string>;
  readonly missing_policy: "fail" | "exclude_with_report";
}

export type HistogramBinningResult = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly result_version: number;
  readonly spec_ref: PlotCalculationSpecRef;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly input_hash: string;
  readonly output_hash: string;
  readonly output_data_ref: ContentTableRef;
  readonly output_table: CalculationTable;
  readonly total_row_count: number;
  readonly included_row_count: number;
  readonly excluded_row_count: number;
  readonly included_row_ids: ReadonlyArray<string>;
  readonly exclusions?: ReadonlyArray<RowExclusion>;
  readonly nonfinite_counts?: NonFiniteCounts;
  readonly fixed_seed?: number | null;
  readonly warnings?: ReadonlyArray<WarningRecord>;
  readonly producer_build_hash: string;
  readonly kind?: "histogram_binning";
  readonly algorithm_id?: "freedman_diaconis_sturges";
  readonly bin_count: number;
  readonly normalization: "count" | "density";
  readonly binning_rule: "freedman_diaconis" | "sturges" | "constant";
}

export type HistogramBinningSpec = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly calculation_version: number;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly log10_fields?: ReadonlyArray<string>;
  readonly fixed_seed?: number | null;
  readonly kind?: "histogram_binning";
  readonly algorithm_id?: "freedman_diaconis_sturges";
  readonly value_field: string;
  readonly normalization?: "count" | "density";
}

export type InputQuestion = {
  readonly question_key: string;
  readonly prompt: string;
  readonly answer_kind: "text" | "single_choice" | "multi_choice" | "field" | "profile";
  readonly choices?: ReadonlyArray<string>;
  readonly required?: boolean;
}

export type IsomorphicConcatSpec = {
  readonly schema_version?: "1.0";
  readonly preparation_spec_id: string;
  readonly preparation_version: number;
  readonly input_refs: ReadonlyArray<SourceDatasetRef>;
  readonly field_mapping_ref: FieldMappingRef;
  readonly compiler_version: string;
  readonly kind?: "isomorphic_concat";
  readonly source_label_kind: "source_sheet" | "source_block" | "source_dataset";
  readonly source_label_field_id: string;
}

export type MatrixProjectionResult = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly result_version: number;
  readonly spec_ref: PlotCalculationSpecRef;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly input_hash: string;
  readonly output_hash: string;
  readonly output_data_ref: ContentTableRef;
  readonly output_table: CalculationTable;
  readonly total_row_count: number;
  readonly included_row_count: number;
  readonly excluded_row_count: number;
  readonly included_row_ids: ReadonlyArray<string>;
  readonly exclusions?: ReadonlyArray<RowExclusion>;
  readonly nonfinite_counts?: NonFiniteCounts;
  readonly fixed_seed?: number | null;
  readonly warnings?: ReadonlyArray<WarningRecord>;
  readonly producer_build_hash: string;
  readonly kind?: "matrix_projection";
  readonly algorithm_id?: "regular_or_unique_xy_projection";
  readonly matrix_rows: number;
  readonly matrix_columns: number;
  readonly complete_grid: boolean;
}

export type MatrixProjectionSpec = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly calculation_version: number;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly log10_fields?: ReadonlyArray<string>;
  readonly fixed_seed?: number | null;
  readonly kind?: "matrix_projection";
  readonly algorithm_id?: "regular_or_unique_xy_projection";
  readonly input_mode: "regular_matrix" | "unique_xy";
  readonly matrix_value_fields?: ReadonlyArray<string>;
  readonly x_field?: string | null;
  readonly y_field?: string | null;
  readonly z_field?: string | null;
}

export type NonFiniteCounts = {
  readonly missing?: number;
  readonly nan?: number;
  readonly positive_inf?: number;
  readonly negative_inf?: number;
}

export type PercentStackResult = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly result_version: number;
  readonly spec_ref: PlotCalculationSpecRef;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly input_hash: string;
  readonly output_hash: string;
  readonly output_data_ref: ContentTableRef;
  readonly output_table: CalculationTable;
  readonly total_row_count: number;
  readonly included_row_count: number;
  readonly excluded_row_count: number;
  readonly included_row_ids: ReadonlyArray<string>;
  readonly exclusions?: ReadonlyArray<RowExclusion>;
  readonly nonfinite_counts?: NonFiniteCounts;
  readonly fixed_seed?: number | null;
  readonly warnings?: ReadonlyArray<WarningRecord>;
  readonly producer_build_hash: string;
  readonly kind?: "percent_stack";
  readonly algorithm_id?: "category_nonnegative_percent";
  readonly category_count: number;
  readonly component_count: number;
}

export type PercentStackSpec = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly calculation_version: number;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly log10_fields?: ReadonlyArray<string>;
  readonly fixed_seed?: number | null;
  readonly kind?: "percent_stack";
  readonly algorithm_id?: "category_nonnegative_percent";
  readonly category_field: string;
  readonly component_field: string;
  readonly value_field: string;
}

export type PlotCalculationResultContract = HistogramBinningResult | TukeyBoxResult | ViolinKDEResult | ECDFResult | SummaryErrorResult | PercentStackResult | MatrixProjectionResult | ConfusionCountResult

export type PlotCalculationSpecContract = HistogramBinningSpec | TukeyBoxSpec | ViolinKDESpec | ECDFSpec | SummaryErrorSpec | PercentStackSpec | MatrixProjectionSpec | ConfusionCountSpec

export type PlotCalculationSpecRef = {
  readonly calculation_id: string;
  readonly calculation_version: number;
  readonly calculation_kind: "histogram_binning" | "tukey_box" | "violin_kde" | "ecdf" | "summary_error" | "percent_stack" | "matrix_projection" | "confusion_count";
  readonly content_hash: string;
}

export type PlotDocument = {
  readonly schema_version?: "2.0";
  readonly plot_id: string;
  readonly plot_version: number;
  readonly parent_version?: number | null;
  readonly profile_id: string;
  readonly data: EngineDataRef;
  readonly bindings: ReadonlyArray<FieldBinding>;
  readonly applied_action_ids?: ReadonlyArray<string>;
}

export type PlotDocumentRef = {
  readonly plot_id: string;
  readonly plot_version: number;
  readonly content_hash: string;
}

export type PlotEngineActionContract = CreatePlot | BindFields | SetTitle | SetAxis | SetSeriesStyle | SetLegend | SetColorMap | SetErrorStyle | SetDataLabels | SetChartParameter | AddAnnotation | ExportPlot

export type PreparationSpecContract = SelectFieldsSpec | ProjectStructureSpec | IsomorphicConcatSpec | ProjectMetadataLabelSpec | ApplyPlotOrderSpec | FilterRowsSpec

export type PreparationSpecRef = {
  readonly preparation_spec_id: string;
  readonly preparation_version: number;
  readonly content_hash: string;
}

export type PreparedDataset = {
  readonly schema_version?: "1.0";
  readonly prepared_dataset_id: string;
  readonly prepared_version: number;
  readonly source_dataset_refs: ReadonlyArray<SourceDatasetRef>;
  readonly field_mapping_ref: FieldMappingRef;
  readonly preparation_spec_ref: PreparationSpecRef;
  readonly compiler_version: string;
  readonly input_hash: string;
  readonly output_hash: string;
  readonly data_ref: ContentTableRef;
  readonly included_row_count: number;
  readonly excluded_row_count: number;
  readonly provenance: PreparedDatasetProvenance;
  readonly warnings?: ReadonlyArray<WarningRecord>;
}

export type PreparedDatasetProvenance = {
  readonly source_coordinate_kinds: ReadonlyArray<"excel" | "text">;
  readonly compiler_build_hash: string;
}

export type PreparedDatasetRef = {
  readonly prepared_dataset_id: string;
  readonly prepared_version: number;
  readonly content_hash: string;
}

export type ProjectMetadataLabelSpec = {
  readonly schema_version?: "1.0";
  readonly preparation_spec_id: string;
  readonly preparation_version: number;
  readonly input_refs: ReadonlyArray<SourceDatasetRef>;
  readonly field_mapping_ref: FieldMappingRef;
  readonly compiler_version: string;
  readonly kind?: "project_metadata_label";
  readonly metadata_key: string;
  readonly output_field_id: string;
}

export type ProjectStructureSpec = {
  readonly schema_version?: "1.0";
  readonly preparation_spec_id: string;
  readonly preparation_version: number;
  readonly input_refs: ReadonlyArray<SourceDatasetRef>;
  readonly field_mapping_ref: FieldMappingRef;
  readonly compiler_version: string;
  readonly kind?: "project_structure";
  readonly input_layout: "wide" | "long" | "matrix";
  readonly output_layout: "wide" | "long" | "matrix";
  readonly role_fields: ReadonlyArray<string>;
}

export type ReshapeLongToWide = {
  readonly operation?: "reshape_long_to_wide";
  readonly source_alias: string;
  readonly index_field_aliases: ReadonlyArray<string>;
  readonly name_field_alias: string;
  readonly value_field_alias: string;
}

export type ReshapeWideToLong = {
  readonly operation?: "reshape_wide_to_long";
  readonly source_alias: string;
  readonly id_field_aliases?: ReadonlyArray<string>;
  readonly value_field_aliases: ReadonlyArray<string>;
  readonly output_name: string;
  readonly output_value: string;
}

export type ResolvedFieldBinding = {
  readonly role: string;
  readonly source_alias: string;
  readonly field_id: string;
}

export type ResolvedWorkflowField = {
  readonly field_alias: string;
  readonly source_alias: string;
  readonly field_id: string;
  readonly name: string;
  readonly logical_type: "numeric" | "categorical" | "datetime" | "boolean" | "text";
  readonly unit_label?: string | null;
}

export type RowExclusion = {
  readonly row_id: string;
  readonly field_id?: string | null;
  readonly reason: "missing" | "nan" | "positive_inf" | "negative_inf";
}

export type SelectFields = {
  readonly operation?: "select_fields";
  readonly source_alias: string;
  readonly field_aliases: ReadonlyArray<string>;
}

export type SelectFieldsSpec = {
  readonly schema_version?: "1.0";
  readonly preparation_spec_id: string;
  readonly preparation_version: number;
  readonly input_refs: ReadonlyArray<SourceDatasetRef>;
  readonly field_mapping_ref: FieldMappingRef;
  readonly compiler_version: string;
  readonly kind?: "select_fields";
  readonly field_ids: ReadonlyArray<string>;
}

export type SetAxis = {
  readonly expected_plot_version: number;
  readonly operation?: "set_axis";
  readonly action_id: string;
  readonly target: string;
  readonly label?: string | null;
  readonly scale?: "linear" | "log10" | "datetime" | "categorical" | null;
  readonly minimum?: number | null;
  readonly maximum?: number | null;
  readonly reverse?: boolean | null;
  readonly title_font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly title_font_size_pt?: number | null;
  readonly title_font_weight?: "normal" | "bold" | null;
  readonly title_italic?: boolean | null;
  readonly title_color?: string | null;
  readonly major_tick_step?: number | null;
  readonly minor_tick_count?: number | null;
  readonly tick_format?: "auto" | "decimal" | "scientific" | "percent" | "date" | "time" | null;
  readonly tick_rotation_deg?: number | null;
  readonly tick_font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly tick_font_size_pt?: number | null;
  readonly tick_color?: string | null;
  readonly axis_line_color?: string | null;
  readonly axis_line_width_pt?: number | null;
  readonly major_grid_visible?: boolean | null;
  readonly minor_grid_visible?: boolean | null;
  readonly grid_color?: string | null;
  readonly grid_line_width_pt?: number | null;
  readonly grid_line_style?: "solid" | "dash" | "dot" | "dash_dot" | "none" | null;
}

export type SetChartParameter = {
  readonly expected_plot_version: number;
  readonly operation?: "set_chart_parameter";
  readonly action_id: string;
  readonly target: string;
  readonly parameter: string;
  readonly value: string | number | boolean;
}

export type SetColorMap = {
  readonly expected_plot_version: number;
  readonly operation?: "set_colormap";
  readonly action_id: string;
  readonly target: string;
  readonly palette?: "viridis" | "plasma" | "inferno" | "magma" | "cividis" | "turbo" | "blue_orange" | "red_white_blue" | "blue_white_red" | "gray_scale" | "fire" | "rainbow_modified" | "cool_warm" | "spectral" | "terrain" | "ocean" | null;
  readonly reverse?: boolean | null;
  readonly minimum?: number | null;
  readonly maximum?: number | null;
  readonly midpoint?: number | null;
  readonly mode?: "continuous" | "discrete" | null;
  readonly levels?: number | null;
  readonly missing_color?: string | null;
  readonly colorbar_visible?: boolean | null;
  readonly colorbar_anchor?: "right" | "bottom" | null;
  readonly colorbar_title?: string | null;
  readonly colorbar_tick_format?: "auto" | "decimal" | "scientific" | "percent" | null;
}

export type SetDataLabels = {
  readonly expected_plot_version: number;
  readonly operation?: "set_data_labels";
  readonly action_id: string;
  readonly target: string;
  readonly visible?: boolean | null;
  readonly value_format?: "auto" | "decimal" | "scientific" | "percent" | null;
  readonly prefix?: string | null;
  readonly suffix?: string | null;
  readonly position?: "auto" | "above" | "below" | "left" | "right" | "center" | null;
  readonly rotation_deg?: number | null;
  readonly font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly font_size_pt?: number | null;
  readonly font_weight?: "normal" | "bold" | null;
  readonly font_color?: string | null;
}

export type SetErrorStyle = {
  readonly expected_plot_version: number;
  readonly operation?: "set_error_style";
  readonly action_id: string;
  readonly target: string;
  readonly bar_color?: string | null;
  readonly bar_width_pt?: number | null;
  readonly cap_size_pt?: number | null;
  readonly bar_opacity?: number | null;
  readonly band_fill_color?: string | null;
  readonly band_fill_opacity?: number | null;
  readonly band_stroke_color?: string | null;
  readonly band_stroke_width_pt?: number | null;
}

export type SetLegend = {
  readonly expected_plot_version: number;
  readonly operation?: "set_legend";
  readonly action_id: string;
  readonly target: string;
  readonly visible?: boolean | null;
  readonly anchor?: "inside" | "inside_top_left" | "inside_top_right" | "inside_bottom_left" | "inside_bottom_right" | "right" | "bottom" | "none" | null;
  readonly columns?: number | null;
  readonly title?: string | null;
  readonly font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly font_size_pt?: number | null;
  readonly font_color?: string | null;
  readonly frame_visible?: boolean | null;
  readonly frame_color?: string | null;
  readonly frame_width_pt?: number | null;
}

export type SetSeriesStyle = {
  readonly expected_plot_version: number;
  readonly operation?: "set_series_style";
  readonly action_id: string;
  readonly target: string;
  readonly line_stroke_color?: string | null;
  readonly line_width_pt?: number | null;
  readonly line_style?: "solid" | "dash" | "dot" | "dash_dot" | "none" | null;
  readonly line_opacity?: number | null;
  readonly marker_shape?: "circle" | "square" | "triangle_up" | "triangle_down" | "triangle_left" | "triangle_right" | "diamond" | "plus" | "cross" | "hexagon" | "star" | "pentagon" | "none" | null;
  readonly marker_size_pt?: number | null;
  readonly marker_interior?: "solid" | "open" | "hollow" | null;
  readonly marker_fill_color?: string | null;
  readonly marker_stroke_color?: string | null;
  readonly marker_stroke_width_pt?: number | null;
  readonly marker_opacity?: number | null;
  readonly fill_color?: string | null;
  readonly fill_opacity?: number | null;
  readonly fill_stroke_color?: string | null;
  readonly fill_stroke_width_pt?: number | null;
  readonly fill_stroke_style?: "solid" | "dash" | "dot" | "dash_dot" | "none" | null;
}

export type SetTitle = {
  readonly expected_plot_version: number;
  readonly operation?: "set_title";
  readonly action_id: string;
  readonly target: string;
  readonly text?: string | null;
  readonly font_family?: "auto" | "Arial" | "Calibri" | "Times New Roman" | "Segoe UI" | "Microsoft YaHei" | "SimSun" | null;
  readonly font_size_pt?: number | null;
  readonly font_weight?: "normal" | "bold" | null;
  readonly italic?: boolean | null;
  readonly color?: string | null;
}

export type SortKey = {
  readonly field_alias: string;
  readonly direction?: "ascending" | "descending";
  readonly missing?: "first" | "last";
}

export type SortRows = {
  readonly operation?: "sort_rows";
  readonly source_alias: string;
  readonly keys: ReadonlyArray<SortKey>;
}

export type SourceDataset = {
  readonly schema_version?: "1.0";
  readonly source_dataset_id: string;
  readonly source_version: number;
  readonly source_object_hash: string;
  readonly content_hash: string;
  readonly import_recipe_version: string;
  readonly parser_version: string;
  readonly unicode_normalization_version: string;
  readonly field_schema: ReadonlyArray<SourceField>;
  readonly data_ref: ContentTableRef;
  readonly quality: DataQualitySummary;
  readonly source_coordinate_samples?: ReadonlyArray<ExcelSourceCoordinate | TextSourceCoordinate>;
}

export type SourceDatasetRef = {
  readonly source_dataset_id: string;
  readonly source_version: number;
  readonly content_hash: string;
}

export type SourceField = {
  readonly field_id: string;
  readonly name: string;
  readonly logical_type: "numeric" | "categorical" | "datetime" | "boolean" | "text";
  readonly physical_type: string;
  readonly unit: UnitSpec;
  readonly source_column_index: number;
  readonly precision_digits?: number | null;
}

export type SummaryErrorResult = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly result_version: number;
  readonly spec_ref: PlotCalculationSpecRef;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly input_hash: string;
  readonly output_hash: string;
  readonly output_data_ref: ContentTableRef;
  readonly output_table: CalculationTable;
  readonly total_row_count: number;
  readonly included_row_count: number;
  readonly excluded_row_count: number;
  readonly included_row_ids: ReadonlyArray<string>;
  readonly exclusions?: ReadonlyArray<RowExclusion>;
  readonly nonfinite_counts?: NonFiniteCounts;
  readonly fixed_seed?: number | null;
  readonly warnings?: ReadonlyArray<WarningRecord>;
  readonly producer_build_hash: string;
  readonly kind?: "summary_error";
  readonly algorithm_id?: "fixed_summary_error";
  readonly method: "mean_sd" | "mean_sem" | "mean_95_t_ci" | "median_iqr" | "median_range" | "direct_bounds" | "direct_symmetric_error";
  readonly group_count: number;
}

export type SummaryErrorSpec = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly calculation_version: number;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly log10_fields?: ReadonlyArray<string>;
  readonly fixed_seed?: number | null;
  readonly kind?: "summary_error";
  readonly algorithm_id?: "fixed_summary_error";
  readonly method: "mean_sd" | "mean_sem" | "mean_95_t_ci" | "median_iqr" | "median_range" | "direct_bounds" | "direct_symmetric_error";
  readonly group_fields?: ReadonlyArray<string>;
  readonly value_field?: string | null;
  readonly center_field?: string | null;
  readonly lower_field?: string | null;
  readonly upper_field?: string | null;
  readonly symmetric_error_field?: string | null;
}

export type TaskDraft = {
  readonly schema_version?: "task-draft.v1";
  readonly draft_id: string;
  readonly workflow_run_id: string;
  readonly route: "deterministic" | "recipe_replay" | "agent_single_turn" | "agent_exploration";
  readonly summary: string;
  readonly items: ReadonlyArray<TaskDraftItem>;
  readonly confidence: number;
  readonly hard_constraints?: ReadonlyArray<string>;
}

export type TaskDraftItem = {
  readonly task_kind: "create" | "edit";
  readonly item_id: string;
  readonly plot_alias: string;
  readonly profile_id: string;
  readonly target_plot_alias?: string | null;
  readonly source_aliases?: ReadonlyArray<string>;
  readonly data_operations?: ReadonlyArray<SelectFields | FilterRows | SortRows | ReshapeLongToWide | ReshapeWideToLong | ConcatenateSources | CalculateChartData>;
  readonly bindings?: ReadonlyArray<DraftFieldBinding>;
  readonly visual_actions?: ReadonlyArray<DraftSetTitle | DraftSetAxis | DraftSetSeriesStyle | DraftSetLegend | DraftSetColorMap | DraftSetErrorStyle | DraftSetDataLabels | DraftSetChartParameter | DraftAddAnnotation>;
}

export type TaskItemProgress = {
  readonly item_id: string;
  readonly state: "pending" | "running" | "succeeded" | "failed" | "blocked" | "cancelled";
  readonly attempt_count?: number;
  readonly error_code?: string | null;
  readonly output_plot_id?: string | null;
  readonly output_plot_version?: number | null;
}

export type TaskPlan = {
  readonly schema_version?: "task-plan.v1";
  readonly plan_id: string;
  readonly workflow_run_id: string;
  readonly draft_hash: string;
  readonly expected_project_revision: number;
  readonly items: ReadonlyArray<CompiledTaskItem>;
}

export type TaskPlanSnapshot = {
  readonly plan: TaskPlan;
  readonly state: "awaiting_confirmation" | "ready" | "running" | "partially_succeeded" | "succeeded" | "failed" | "rejected" | "cancelled";
  readonly current_project_revision: number;
  readonly item_progress: ReadonlyArray<TaskItemProgress>;
  readonly created_at: string;
  readonly updated_at: string;
}

export type TextSourceCoordinate = {
  readonly kind?: "text";
  readonly byte_start: number;
  readonly byte_end: number;
  readonly line_start: number;
  readonly line_end: number;
  readonly block?: string | null;
  readonly channel?: string | null;
  readonly sweep?: string | null;
  readonly source_row_id: string;
}

export type TukeyBoxResult = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly result_version: number;
  readonly spec_ref: PlotCalculationSpecRef;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly input_hash: string;
  readonly output_hash: string;
  readonly output_data_ref: ContentTableRef;
  readonly output_table: CalculationTable;
  readonly total_row_count: number;
  readonly included_row_count: number;
  readonly excluded_row_count: number;
  readonly included_row_ids: ReadonlyArray<string>;
  readonly exclusions?: ReadonlyArray<RowExclusion>;
  readonly nonfinite_counts?: NonFiniteCounts;
  readonly fixed_seed?: number | null;
  readonly warnings?: ReadonlyArray<WarningRecord>;
  readonly producer_build_hash: string;
  readonly kind?: "tukey_box";
  readonly algorithm_id?: "linear_quantile_tukey_1_5_iqr";
  readonly group_count: number;
}

export type TukeyBoxSpec = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly calculation_version: number;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly log10_fields?: ReadonlyArray<string>;
  readonly fixed_seed?: number | null;
  readonly kind?: "tukey_box";
  readonly algorithm_id?: "linear_quantile_tukey_1_5_iqr";
  readonly value_field: string;
  readonly group_field?: string | null;
}

export type UnitSpec = {
  readonly source_text: string;
  readonly canonical_unit?: string | null;
  readonly dimensionality: string;
  readonly kind: "recognized" | "opaque" | "dimensionless";
  readonly registry_version: string;
}

export type ViolinKDEResult = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly result_version: number;
  readonly spec_ref: PlotCalculationSpecRef;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly input_hash: string;
  readonly output_hash: string;
  readonly output_data_ref: ContentTableRef;
  readonly output_table: CalculationTable;
  readonly total_row_count: number;
  readonly included_row_count: number;
  readonly excluded_row_count: number;
  readonly included_row_ids: ReadonlyArray<string>;
  readonly exclusions?: ReadonlyArray<RowExclusion>;
  readonly nonfinite_counts?: NonFiniteCounts;
  readonly fixed_seed?: number | null;
  readonly warnings?: ReadonlyArray<WarningRecord>;
  readonly producer_build_hash: string;
  readonly kind?: "violin_kde";
  readonly algorithm_id?: "gaussian_scott_observed_range";
  readonly group_count: number;
  readonly grid_points?: 256;
  readonly bandwidths: ReadonlyArray<number>;
}

export type ViolinKDESpec = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly calculation_version: number;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly log10_fields?: ReadonlyArray<string>;
  readonly fixed_seed?: number | null;
  readonly kind?: "violin_kde";
  readonly algorithm_id?: "gaussian_scott_observed_range";
  readonly value_field: string;
  readonly group_field?: string | null;
  readonly grid_points?: 256;
}

export type WarningRecord = {
  readonly warning_id: string;
  readonly message: string;
}

export type WorkflowBudget = {
  readonly max_agent_turns?: number;
  readonly max_tool_calls?: number;
  readonly max_preview_rows?: number;
  readonly max_profiled_fields?: number;
  readonly max_disclosed_scalars?: number;
}

export type WorkflowContext = {
  readonly schema_version?: "workflow-context.v1";
  readonly workflow_run_id: string;
  readonly project_id: string;
  readonly project_revision: number;
  readonly instruction: string;
  readonly locale?: "zh-CN" | "en-US";
  readonly sources?: ReadonlyArray<WorkflowSource>;
  readonly fields?: ReadonlyArray<WorkflowField>;
  readonly plots?: ReadonlyArray<WorkflowPlot>;
  readonly selected_source_aliases?: ReadonlyArray<string>;
  readonly selected_plot_aliases?: ReadonlyArray<string>;
  readonly selected_profile_ids?: ReadonlyArray<string>;
  readonly allowed_profile_ids: ReadonlyArray<string>;
  readonly budget: WorkflowBudget;
}

export type WorkflowDecisionContract = WorkflowNeedsInput | WorkflowUnsupported | WorkflowDraftReady

export type WorkflowDraftReady = {
  readonly outcome?: "draft_ready";
  readonly draft: TaskDraft;
}

export type WorkflowField = {
  readonly field_alias: string;
  readonly source_alias: string;
  readonly field_id: string;
  readonly name: string;
  readonly logical_type: "numeric" | "categorical" | "datetime" | "boolean" | "text";
  readonly unit_label?: string | null;
}

export type WorkflowNeedsInput = {
  readonly outcome?: "needs_input";
  readonly workflow_run_id: string;
  readonly questions: ReadonlyArray<InputQuestion>;
}

export type WorkflowPlot = {
  readonly plot_alias: string;
  readonly plot_id: string;
  readonly plot_version: number;
  readonly profile_id: string;
}

export type WorkflowRecipe = {
  readonly schema_version?: "workflow-recipe.v1";
  readonly recipe_id: string;
  readonly recipe_version: number;
  readonly display_name: string;
  readonly structure_fingerprint: string;
  readonly goal_signature: string;
  readonly draft_template: TaskDraft;
  readonly engine_profile_hash: string;
  readonly renderer_contract_hash: string;
  readonly created_from_workflow_run_id: string;
  readonly created_from_plan_id: string;
  readonly created_from_export_hash: string;
  readonly archived?: boolean;
}

export type WorkflowRunSnapshot = {
  readonly workflow_run_id: string;
  readonly project_id: string;
  readonly state: "routing" | "deterministic_attempt" | "recipe_matching" | "recipe_replay" | "agent_single_turn" | "agent_exploration" | "needs_input" | "draft_ready" | "awaiting_confirmation" | "executing" | "completed" | "partially_succeeded" | "failed" | "cancelled";
  readonly route?: "deterministic" | "recipe_replay" | "agent_single_turn" | "agent_exploration" | "needs_input" | "unsupported" | null;
  readonly context_hash?: string | null;
  readonly draft_id?: string | null;
  readonly plan_id?: string | null;
  readonly model_turn_count?: number;
  readonly tool_call_count?: number;
  readonly input_token_count?: number;
  readonly output_token_count?: number;
  readonly estimated_cost?: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export type WorkflowSource = {
  readonly source_alias: string;
  readonly source_dataset_id: string;
  readonly source_version: number;
  readonly content_hash: string;
  readonly display_name: string;
  readonly row_count: number;
}

export type WorkflowUnsupported = {
  readonly outcome?: "unsupported";
  readonly workflow_run_id: string;
  readonly reason_code: string;
  readonly message: string;
}
