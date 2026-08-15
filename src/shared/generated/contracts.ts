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
}

export type AgentAddAnnotation = {
  readonly operation?: "add_annotation";
  readonly action_id: string;
  readonly plot_alias: string;
  readonly annotation_alias: string;
  readonly text: string;
  readonly x: number;
  readonly y: number;
  readonly coordinate_system?: "data" | "axes" | "page";
}

export type AgentBindFields = {
  readonly operation?: "bind_fields";
  readonly action_id: string;
  readonly plot_alias: string;
  readonly source_alias: string;
  readonly bindings: ReadonlyArray<AgentFieldBinding>;
}

export type AgentCreatePlot = {
  readonly operation?: "create_plot";
  readonly action_id: string;
  readonly plot_alias: string;
  readonly profile_id: string;
  readonly source_alias: string;
  readonly bindings: ReadonlyArray<AgentFieldBinding>;
}

export type AgentExportPlot = {
  readonly operation?: "export_plot";
  readonly action_id: string;
  readonly plot_alias: string;
  readonly format: "png" | "svg" | "opju";
  readonly output_name: string;
}

export type AgentFieldBinding = {
  readonly role: string;
  readonly field_alias: string;
}

export type AgentSetAxis = {
  readonly operation?: "set_axis";
  readonly action_id: string;
  readonly plot_alias: string;
  readonly axis_alias: string;
  readonly label?: string | null;
  readonly scale?: "linear" | "log10" | "datetime" | "categorical" | null;
  readonly minimum?: number | null;
  readonly maximum?: number | null;
  readonly reverse?: boolean | null;
}

export type AgentSetChartParameter = {
  readonly operation?: "set_chart_parameter";
  readonly action_id: string;
  readonly plot_alias: string;
  readonly parameter: string;
  readonly value: string | number | boolean;
}

export type AgentSetLegend = {
  readonly operation?: "set_legend";
  readonly action_id: string;
  readonly plot_alias: string;
  readonly visible?: boolean | null;
  readonly anchor?: "inside" | "right" | "bottom" | "none" | null;
}

export type AgentSetSeriesStyle = {
  readonly operation?: "set_series_style";
  readonly action_id: string;
  readonly plot_alias: string;
  readonly series_alias: string;
  readonly color?: string | null;
  readonly line_width_pt?: number | null;
  readonly line_style?: "solid" | "dash" | "dot" | "dash_dot" | "none" | null;
  readonly symbol?: string | null;
  readonly symbol_size_pt?: number | null;
}

export type AgentSetTitle = {
  readonly operation?: "set_title";
  readonly action_id: string;
  readonly plot_alias: string;
  readonly text: string;
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

export type BoundEnginePlan = {
  readonly plan_id: string;
  readonly expected_project_revision: number;
  readonly actions: ReadonlyArray<CreatePlot | BindFields | SetTitle | SetAxis | SetSeriesStyle | SetLegend | SetChartParameter | AddAnnotation | ExportPlot>;
}

export type CalculationTable = {
  readonly field_ids: ReadonlyArray<string>;
  readonly rows: ReadonlyArray<ReadonlyArray<string | boolean | number | null>>;
}

export type ChartCapabilities = {
  readonly capability_version: string;
  readonly allowed_chart_type_ids?: ReadonlyArray<"K01" | "K02" | "K03" | "K04" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "S34" | "S61" | "X02" | "X03" | "X05" | "X09" | "X13" | "X23" | "X24" | "X35" | "X36" | "X38" | "X39" | "X40">;
  readonly allowed_action_types: ReadonlyArray<"create_plot" | "bind_fields" | "set_title" | "set_axis" | "set_series_style" | "set_legend" | "set_chart_parameter" | "add_annotation" | "export_plot">;
  readonly export_formats?: ReadonlyArray<"png" | "svg" | "opju">;
  readonly limitation_ids?: ReadonlyArray<string>;
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

export type ContextEnvelope = {
  readonly schema_version?: "1.0";
  readonly prompt_template_version: string;
  readonly locale: string;
  readonly user_instruction: string;
  readonly target_snapshot: ContextObjectRef;
  readonly conversation_state: ConversationStateProjection;
  readonly chart_capabilities: ChartCapabilities;
  readonly selected_context: SelectedContext;
  readonly data_disclosure: DataDisclosure;
  readonly context_hash: string;
}

export type ContextField = {
  readonly field_alias: string;
  readonly field_id: string;
  readonly name: string;
  readonly logical_type: "numeric" | "categorical" | "datetime" | "boolean" | "text";
  readonly unit_text?: string;
  readonly semantic_role?: string | null;
  readonly summary?: ContextFieldSummary | null;
}

export type ContextFieldBinding = {
  readonly field_alias: string;
  readonly field_id: string;
  readonly source_dataset_id: string;
  readonly source_version: number;
}

export type ContextFieldSummary = {
  readonly valid_count: number;
  readonly missing_count: number;
  readonly nan_count?: number;
  readonly positive_inf_count?: number;
  readonly negative_inf_count?: number;
  readonly distinct_count?: number | null;
  readonly numeric_minimum?: number | null;
  readonly numeric_maximum?: number | null;
}

export type ContextMessage = {
  readonly role: "user" | "assistant";
  readonly text: string;
}

export type ContextObjectRef = {
  readonly object_alias: string;
  readonly object_id: string;
  readonly object_version: number;
  readonly object_type: "source_dataset" | "prepared_dataset" | "plot" | "export" | "project";
  readonly content_hash?: string | null;
  readonly display_name?: string | null;
}

export type ContextSampleRow = {
  readonly sample_key: string;
  readonly values: Readonly<Record<string, never>>;
}

export type ConversationStateProjection = {
  readonly state_version: number;
  readonly current_target: ContextObjectRef;
  readonly selected_objects?: ReadonlyArray<ContextObjectRef>;
  readonly confirmed_field_aliases?: ReadonlyArray<string>;
  readonly project_rule_ids?: ReadonlyArray<string>;
  readonly saved_setting_refs?: ReadonlyArray<string>;
  readonly unresolved_question_ids?: ReadonlyArray<string>;
  readonly recent_result_kinds?: ReadonlyArray<"action_plan" | "needs_input" | "unsupported" | "no_change" | "execution_result">;
}

export type CreatePlot = {
  readonly operation?: "create_plot";
  readonly action_id: string;
  readonly plot_id: string;
  readonly profile_id: string;
  readonly data: EngineDataRef;
  readonly bindings: ReadonlyArray<FieldBinding>;
}

export type DataDisclosure = {
  readonly provider_type: "builtin" | "custom";
  readonly provider_config_id: string;
  readonly authorization_scope: "default_consent" | "this_run" | "this_conversation_similar";
  readonly retention_disclosure_version: string;
  readonly categories: ReadonlyArray<"user_instruction" | "field_metadata" | "statistics" | "sample" | "message_window" | "chart_capabilities">;
  readonly field_aliases: ReadonlyArray<string>;
  readonly field_count: number;
  readonly row_count: number;
  readonly scalar_count: number;
  readonly disclosure_hash: string;
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

export type EngineAgentDecisionContract = EngineAgentPlan | NeedsInput | Unsupported | NoChange

export type EngineAgentPlan = {
  readonly schema_version?: "engine-agent.v1";
  readonly decision_type?: "action_plan";
  readonly plan_id: string;
  readonly target_alias: string;
  readonly actions: ReadonlyArray<AgentCreatePlot | AgentBindFields | AgentSetTitle | AgentSetAxis | AgentSetSeriesStyle | AgentSetLegend | AgentSetChartParameter | AgentAddAnnotation | AgentExportPlot>;
}

export type EngineArtifact = {
  readonly backend: "matplotlib" | "origin";
  readonly format: "png" | "svg" | "opju";
  readonly artifact_hash: string;
  readonly artifact_size: number;
}

export type EngineCapability = {
  readonly operation: "create_plot" | "bind_fields" | "set_title" | "set_axis" | "set_series_style" | "set_legend" | "set_chart_parameter" | "add_annotation" | "export_plot";
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

export type InputChoice = {
  readonly value: string;
  readonly label: string;
}

export type InputQuestion = {
  readonly question_key: string;
  readonly prompt: string;
  readonly input_kind: "single_choice" | "multiple_choice" | "number" | "text";
  readonly choices?: ReadonlyArray<InputChoice>;
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

export type NeedsInput = {
  readonly schema_version?: "engine-agent.v1";
  readonly decision_type?: "needs_input";
  readonly target_alias: string;
  readonly questions: ReadonlyArray<InputQuestion>;
}

export type NoChange = {
  readonly schema_version?: "engine-agent.v1";
  readonly decision_type?: "no_change";
  readonly target_alias: string;
  readonly explanation: string;
}

export type NonFiniteCounts = {
  readonly missing?: number;
  readonly nan?: number;
  readonly positive_inf?: number;
  readonly negative_inf?: number;
}

export type NonFiniteSampleValue = {
  readonly kind?: "nonfinite";
  readonly value: "nan" | "positive_inf" | "negative_inf";
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

export type PlotEngineActionContract = CreatePlot | BindFields | SetTitle | SetAxis | SetSeriesStyle | SetLegend | SetChartParameter | AddAnnotation | ExportPlot

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

export type ProjectContextSnapshot = {
  readonly schema_version?: "1.0";
  readonly snapshot_id: string;
  readonly snapshot_hash: string;
  readonly project_id: string;
  readonly project_revision: number;
  readonly conversation_id: string;
  readonly conversation_state: ConversationStateProjection;
  readonly known_objects?: ReadonlyArray<ContextObjectRef>;
  readonly recent_result_objects?: ReadonlyArray<ContextObjectRef>;
  readonly field_bindings?: ReadonlyArray<ContextFieldBinding>;
  readonly project_rule_ids?: ReadonlyArray<string>;
  readonly saved_setting_refs?: ReadonlyArray<string>;
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

export type RowExclusion = {
  readonly row_id: string;
  readonly field_id?: string | null;
  readonly reason: "missing" | "nan" | "positive_inf" | "negative_inf";
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

export type SelectedContext = {
  readonly fields?: ReadonlyArray<ContextField>;
  readonly sample_rows?: ReadonlyArray<ContextSampleRow>;
  readonly selected_objects?: ReadonlyArray<ContextObjectRef>;
  readonly message_window?: ReadonlyArray<ContextMessage>;
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
}

export type SetChartParameter = {
  readonly expected_plot_version: number;
  readonly operation?: "set_chart_parameter";
  readonly action_id: string;
  readonly target: string;
  readonly parameter: string;
  readonly value: string | number | boolean;
}

export type SetLegend = {
  readonly expected_plot_version: number;
  readonly operation?: "set_legend";
  readonly action_id: string;
  readonly target: string;
  readonly visible?: boolean | null;
  readonly anchor?: "inside" | "right" | "bottom" | "none" | null;
}

export type SetSeriesStyle = {
  readonly expected_plot_version: number;
  readonly operation?: "set_series_style";
  readonly action_id: string;
  readonly target: string;
  readonly color?: string | null;
  readonly line_width_pt?: number | null;
  readonly line_style?: "solid" | "dash" | "dot" | "dash_dot" | "none" | null;
  readonly symbol?: string | null;
  readonly symbol_size_pt?: number | null;
}

export type SetTitle = {
  readonly expected_plot_version: number;
  readonly operation?: "set_title";
  readonly action_id: string;
  readonly target: string;
  readonly text: string;
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

export type Unsupported = {
  readonly schema_version?: "engine-agent.v1";
  readonly decision_type?: "unsupported";
  readonly target_alias: string;
  readonly category: "provider_capability" | "profile_capability" | "data_requirement";
  readonly explanation: string;
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
