// Generated from schemas/contracts-bundle.schema.json. Do not edit.

export const CONTRACT_SCHEMA_VERSION = "1.0" as const

export type ActionPlan = {
  readonly schema_version?: "1.0";
  readonly decision_type?: "action_plan";
  readonly plan_id: string;
  readonly target_alias: string;
  readonly actions: ReadonlyArray<CreatePlotAction | PatchPlotAction | CreateBatchAction | PatchBatchAction | CreateFigureAction | PatchFigureAction | ExportArtifactAction>;
  readonly warnings?: ReadonlyArray<PlanWarning>;
  readonly confirmation?: "not_required" | "required";
}

export type AddAnnotationPatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "add_annotation";
  readonly annotation: AnnotationSpec;
}

export type AgentDecisionContract = ActionPlan | NeedsInput | Unsupported | NoChange

export type AnnotationSpec = {
  readonly annotation_id: string;
  readonly kind: "text" | "arrow" | "line" | "rectangle" | "reference_line" | "reference_band" | "peak_label" | "significance_bracket" | "panel_label";
  readonly text?: SafeRichText | null;
  readonly x?: number | null;
  readonly y?: number | null;
  readonly affect_range?: boolean;
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

export type ApplyPublicationProfilePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "apply_publication_profile";
  readonly profile: PublicationProfileSnapshot;
}

export type AxisLabelIntent = {
  readonly operation?: "set_axis_label";
  readonly target_alias: string;
  readonly label: string;
}

export type AxisRange = {
  readonly minimum?: number | null;
  readonly maximum?: number | null;
  readonly reverse?: boolean;
}

export type AxisRangeIntent = {
  readonly operation?: "set_axis_range";
  readonly target_alias: string;
  readonly minimum: number;
  readonly maximum: number;
}

export type AxisScaleIntent = {
  readonly operation?: "set_axis_scale";
  readonly target_alias: string;
  readonly scale: "linear" | "log10" | "datetime" | "categorical";
}

export type AxisSpec = {
  readonly axis_id: string;
  readonly scale_id: string;
  readonly orientation: "x" | "y" | "color";
  readonly position: "bottom" | "top" | "left" | "right" | "none";
  readonly label: SafeRichText;
}

export type BatchItemState = {
  readonly item_id: string;
  readonly state: "pending" | "succeeded" | "failed" | "excluded";
  readonly error_code?: string | null;
}

export type BatchPlotOverride = {
  readonly item_id: string;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly patches?: ReadonlyArray<SetAxisRangePatch | SetAxisScalePatch | SetAxisLabelPatch | SetSeriesStylePatch | SetCategoryColorPatch | MoveLegendPatch | SetLegendVisibilityPatch | AddAnnotationPatch | UpdateAnnotationPatch | RemoveAnnotationPatch | ApplyPublicationProfilePatch | SetCanvasSizePatch | SetBatchAxisPolicyPatch>;
}

export type BatchSpec = {
  readonly schema_version?: "1.0";
  readonly batch_id: string;
  readonly batch_version: number;
  readonly dataset_signature: DatasetSignature;
  readonly dataset_version_refs: ReadonlyArray<PreparedDatasetRef>;
  readonly shared_field_mapping: FieldMappingRef;
  readonly plot_template_ref: PlotSpecRef;
  readonly shared_style: ResolvedStyleSnapshot;
  readonly axis_policy?: "per_plot" | "unified";
  readonly plot_overrides?: ReadonlyArray<BatchPlotOverride>;
  readonly item_states: ReadonlyArray<BatchItemState>;
}

export type CalculatedSeriesData = {
  readonly kind?: "calculated";
  readonly calculation_result_ref: PlotCalculationResultRef;
  readonly role_fields: ReadonlyArray<string>;
}

export type CalculationTable = {
  readonly field_ids: ReadonlyArray<string>;
  readonly rows: ReadonlyArray<ReadonlyArray<string | boolean | number | null>>;
}

export type CanvasSizeIntent = {
  readonly operation?: "set_canvas_size";
  readonly target_alias: string;
  readonly physical_size: PhysicalSize;
}

export type CategoricalFamily = {
  readonly kind?: "categorical";
  readonly geometry: ReadonlyArray<"bar">;
}

export type ChartRegistration = {
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61";
  readonly english_name: string;
  readonly family: "xy" | "categorical" | "distribution" | "matrix" | "survival" | "dose_response" | "forest" | "facet";
  readonly geometries: ReadonlyArray<"line" | "symbol" | "error_bar" | "band" | "area" | "bar" | "strip" | "box" | "violin" | "histogram" | "density" | "step" | "heatmap" | "contour" | "risk_table" | "interval" | "panel">;
  readonly required_roles: ReadonlyArray<string>;
  readonly optional_roles?: ReadonlyArray<string>;
  readonly required_calculations?: ReadonlyArray<"histogram_binning" | "tukey_box" | "violin_kde" | "density_kde" | "ecdf" | "summary_error" | "percent_stack" | "matrix_projection" | "confusion_count">;
  readonly allowed_calculations?: ReadonlyArray<"histogram_binning" | "tukey_box" | "violin_kde" | "density_kde" | "ecdf" | "summary_error" | "percent_stack" | "matrix_projection" | "confusion_count">;
  readonly required_precomputed?: ReadonlyArray<"curve" | "band" | "matrix" | "matrix_grid" | "step_curve" | "risk_table" | "parameter_table" | "spectrum" | "peak_labels" | "complex_curve" | "effect_interval">;
  readonly exports?: ExportCapabilities;
}

export type ChartRegistry = {
  readonly schema_version?: "1.0";
  readonly charts: ReadonlyArray<ChartRegistration>;
}

export type ColorValue = {
  readonly value: string;
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
  readonly normalization?: "count" | "true_class" | "predicted_class";
  readonly category_order?: ReadonlyArray<string>;
}

export type ContentTableRef = {
  readonly object_hash: string;
  readonly row_count: number;
  readonly field_ids: ReadonlyArray<string>;
}

export type CreateBatchAction = {
  readonly action_id: string;
  readonly depends_on?: ReadonlyArray<string>;
  readonly action_type?: "create_batch";
  readonly target_alias: string;
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61";
  readonly field_selections: ReadonlyArray<SemanticFieldSelection>;
  readonly axis_policy?: "per_plot" | "unified";
}

export type CreateFigureAction = {
  readonly action_id: string;
  readonly depends_on?: ReadonlyArray<string>;
  readonly action_type?: "create_figure";
  readonly target_alias: string;
  readonly plot_aliases: ReadonlyArray<string>;
  readonly layout: "1x2" | "2x1" | "2x2";
}

export type CreatePlotAction = {
  readonly action_id: string;
  readonly depends_on?: ReadonlyArray<string>;
  readonly action_type?: "create_plot";
  readonly target_alias: string;
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61";
  readonly field_selections: ReadonlyArray<SemanticFieldSelection>;
}

export type DataIntegritySnapshot = {
  readonly total_rows: number;
  readonly visible_rows: number;
  readonly excluded_rows: number;
  readonly nonfinite_values: number;
  readonly simplification_applied: boolean;
  readonly full_data_hash: string;
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

export type DatasetFieldSignature = {
  readonly field_id: string;
  readonly logical_type: "numeric" | "categorical" | "datetime" | "boolean" | "text";
  readonly unit_hash: string;
  readonly semantic_role: string;
}

export type DatasetSignature = {
  readonly fields: ReadonlyArray<DatasetFieldSignature>;
  readonly semantic_hash: string;
}

export type DensityKDEResult = {
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
  readonly kind?: "density_kde";
  readonly algorithm_id?: "gaussian_scott_three_bandwidth";
  readonly group_count: number;
  readonly grid_points?: 256;
  readonly bandwidths: ReadonlyArray<number>;
}

export type DensityKDESpec = {
  readonly schema_version?: "1.0";
  readonly calculation_id: string;
  readonly calculation_version: number;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly algorithm_version: string;
  readonly missing_policy: "fail" | "exclude_with_report";
  readonly log10_fields?: ReadonlyArray<string>;
  readonly fixed_seed?: number | null;
  readonly kind?: "density_kde";
  readonly algorithm_id?: "gaussian_scott_three_bandwidth";
  readonly value_field: string;
  readonly group_field?: string | null;
  readonly grid_points?: 256;
}

export type DistributionFamily = {
  readonly kind?: "distribution";
  readonly geometry: ReadonlyArray<"strip" | "box" | "violin" | "histogram" | "density" | "step">;
}

export type DoseResponseFamily = {
  readonly kind?: "dose_response";
  readonly geometry: ReadonlyArray<"symbol" | "line" | "band">;
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

export type ExportArtifactAction = {
  readonly action_id: string;
  readonly depends_on?: ReadonlyArray<string>;
  readonly action_type?: "export_artifact";
  readonly target_alias: string;
  readonly format: "png" | "svg" | "opju";
  readonly target_scope: "current_plot" | "selected_plots" | "batch" | "figure";
  readonly output_name: string;
}

export type ExportCapabilities = {
  readonly png?: true;
  readonly svg?: true;
  readonly opju?: "O0" | "O1" | "O2" | "O3";
}

export type ExportSpec = {
  readonly schema_version?: "1.0";
  readonly export_id: string;
  readonly export_version: number;
  readonly format: "png" | "svg" | "opju";
  readonly target_scope: "current_plot" | "selected_plots" | "batch" | "figure";
  readonly target_refs: ReadonlyArray<ObjectVersionRef>;
  readonly target_resource: ResourceRef;
  readonly output_name: string;
  readonly render_plan_hash: string;
  readonly validation?: ExportValidationRequirements;
}

export type ExportSpecRef = {
  readonly export_id: string;
  readonly export_version: number;
  readonly content_hash: string;
}

export type ExportValidationRequirements = {
  readonly validate_structure?: true;
  readonly validate_dimensions?: true;
  readonly validate_content?: true;
  readonly require_fresh_reopen?: boolean;
}

export type FacetFamily = {
  readonly kind?: "facet";
  readonly geometry: ReadonlyArray<"panel">;
}

export type FieldMapping = {
  readonly schema_version?: "1.0";
  readonly field_mapping_id: string;
  readonly mapping_version: number;
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61";
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

export type FigurePanel = {
  readonly panel_id: string;
  readonly plot_version_ref: PlotSpecRef;
  readonly panel_label: SafeRichText;
}

export type FigureSpec = {
  readonly schema_version?: "1.0";
  readonly figure_id: string;
  readonly figure_version: number;
  readonly layout: "1x2" | "2x1" | "2x2";
  readonly panels: ReadonlyArray<FigurePanel>;
  readonly common_legend: boolean;
  readonly physical_size: PhysicalSize;
  readonly publication_profile: PublicationProfileSnapshot;
}

export type ForestFamily = {
  readonly kind?: "forest";
  readonly geometry: ReadonlyArray<"interval" | "symbol">;
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
  readonly source_label_kind: "source_sheet" | "source_block";
  readonly source_label_field_id: string;
}

export type LegendPlacementIntent = {
  readonly operation?: "move_legend";
  readonly target_alias: string;
  readonly placement: "inside" | "outside_right" | "outside_bottom";
}

export type LegendVisibilityIntent = {
  readonly operation?: "set_legend_visibility";
  readonly target_alias: string;
  readonly visible: boolean;
}

export type MaskForPlotSpec = {
  readonly schema_version?: "1.0";
  readonly preparation_spec_id: string;
  readonly preparation_version: number;
  readonly input_refs: ReadonlyArray<SourceDatasetRef>;
  readonly field_mapping_ref: FieldMappingRef;
  readonly compiler_version: string;
  readonly kind?: "mask_for_plot";
  readonly field_ids: ReadonlyArray<string>;
  readonly missing_policy: "fail" | "exclude_with_report";
}

export type MatrixFamily = {
  readonly kind?: "matrix";
  readonly geometry: ReadonlyArray<"heatmap" | "contour">;
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

export type MoveLegendPatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "move_legend";
  readonly placement: "inside" | "outside_right" | "outside_bottom";
  readonly anchor_x: number;
  readonly anchor_y: number;
}

export type NeedsInput = {
  readonly schema_version?: "1.0";
  readonly decision_type?: "needs_input";
  readonly target_alias: string;
  readonly questions: ReadonlyArray<InputQuestion>;
}

export type NoChange = {
  readonly schema_version?: "1.0";
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

export type ObjectVersionRef = {
  readonly object_id: string;
  readonly expected_version: number;
}

export type OriginBooleanProperty = {
  readonly value_kind?: "boolean";
  readonly target_id: string;
  readonly property_name: "axis.reverse" | "legend.visible";
  readonly value: boolean;
}

export type OriginColorProperty = {
  readonly value_kind?: "color";
  readonly target_id: string;
  readonly property_name?: "plot.color";
  readonly value: ColorValue;
}

export type OriginDataObject = {
  readonly object_id: string;
  readonly object_kind: "worksheet" | "matrixbook";
  readonly folder: "Data" | "Analysis";
  readonly internal_name: string;
  readonly long_name: string;
  readonly data_ref: ContentTableRef;
}

export type OriginExactVersion = {
  readonly version: string;
  readonly build: string;
  readonly bitness?: "x64";
}

export type OriginExportPlan = {
  readonly schema_version?: "1.0";
  readonly origin_plan_id: string;
  readonly origin_plan_version: number;
  readonly export_spec_ref: ExportSpecRef;
  readonly render_plan_hash: string;
  readonly adapter_id: string;
  readonly adapter_version: string;
  readonly capability?: "O1";
  readonly origin_version: OriginExactVersion;
  readonly template: OriginTemplateRef;
  readonly project_folders?: "Data/Analysis/Graphs/Metadata";
  readonly data_objects: ReadonlyArray<OriginDataObject>;
  readonly graph_objects: ReadonlyArray<OriginGraphObject>;
  readonly property_assignments?: ReadonlyArray<OriginNumericProperty | OriginBooleanProperty | OriginScaleProperty | OriginColorProperty>;
  readonly validation?: OriginValidationPlan;
}

export type OriginGraphObject = {
  readonly graph_id: string;
  readonly folder?: "Graphs";
  readonly internal_name: string;
  readonly long_name: string;
  readonly layer_ids: ReadonlyArray<string>;
  readonly data_object_ids: ReadonlyArray<string>;
}

export type OriginNumericProperty = {
  readonly value_kind?: "number";
  readonly target_id: string;
  readonly property_name: "page.width_mm" | "page.height_mm" | "layer.left_mm" | "layer.top_mm" | "layer.width_mm" | "layer.height_mm" | "axis.minimum" | "axis.maximum" | "plot.line_width_pt" | "plot.marker_size_pt";
  readonly value: number;
}

export type OriginScaleProperty = {
  readonly value_kind?: "scale";
  readonly target_id: string;
  readonly property_name?: "axis.scale";
  readonly value: "linear" | "log10" | "datetime" | "categorical";
}

export type OriginTemplateRef = {
  readonly template_resource: ResourceRef;
  readonly template_hash: string;
  readonly signature_hash: string;
}

export type OriginValidationPlan = {
  readonly live_structural_validation?: true;
  readonly fresh_reopen_validation?: true;
  readonly require_no_external_links?: true;
  readonly require_atomic_publish?: true;
}

export type PatchBatchAction = {
  readonly action_id: string;
  readonly depends_on?: ReadonlyArray<string>;
  readonly action_type?: "patch_batch";
  readonly target_alias: string;
  readonly axis_policy: "per_plot" | "unified";
}

export type PatchFigureAction = {
  readonly action_id: string;
  readonly depends_on?: ReadonlyArray<string>;
  readonly action_type?: "patch_figure";
  readonly target_alias: string;
  readonly panel_alias: string;
  readonly replacement_plot_alias: string;
}

export type PatchPlotAction = {
  readonly action_id: string;
  readonly depends_on?: ReadonlyArray<string>;
  readonly action_type?: "patch_plot";
  readonly target_alias: string;
  readonly patches: ReadonlyArray<AxisRangeIntent | AxisScaleIntent | AxisLabelIntent | SeriesStyleIntent | LegendVisibilityIntent | LegendPlacementIntent | PublicationProfileIntent | CanvasSizeIntent>;
}

export type PatchTransaction = {
  readonly schema_version?: "1.0";
  readonly transaction_id: string;
  readonly project_id: string;
  readonly expected_versions: ReadonlyArray<ObjectVersionRef>;
  readonly patches: ReadonlyArray<SetAxisRangePatch | SetAxisScalePatch | SetAxisLabelPatch | SetSeriesStylePatch | SetCategoryColorPatch | MoveLegendPatch | SetLegendVisibilityPatch | AddAnnotationPatch | UpdateAnnotationPatch | RemoveAnnotationPatch | ApplyPublicationProfilePatch | SetCanvasSizePatch | SetBatchAxisPolicyPatch>;
  readonly scope: "plot" | "selected_plots" | "batch";
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

export type PhysicalLength = {
  readonly value: number;
  readonly unit: "mm" | "pt";
}

export type PhysicalSize = {
  readonly width: PhysicalLength;
  readonly height: PhysicalLength;
}

export type PlanWarning = {
  readonly category: "scientific" | "compatibility" | "scope";
  readonly message: string;
}

export type PlotCalculationResultContract = HistogramBinningResult | TukeyBoxResult | ViolinKDEResult | DensityKDEResult | ECDFResult | SummaryErrorResult | PercentStackResult | MatrixProjectionResult | ConfusionCountResult

export type PlotCalculationResultRef = {
  readonly calculation_id: string;
  readonly result_version: number;
  readonly calculation_kind: "histogram_binning" | "tukey_box" | "violin_kde" | "density_kde" | "ecdf" | "summary_error" | "percent_stack" | "matrix_projection" | "confusion_count";
  readonly content_hash: string;
}

export type PlotCalculationSpecContract = HistogramBinningSpec | TukeyBoxSpec | ViolinKDESpec | DensityKDESpec | ECDFSpec | SummaryErrorSpec | PercentStackSpec | MatrixProjectionSpec | ConfusionCountSpec

export type PlotCalculationSpecRef = {
  readonly calculation_id: string;
  readonly calculation_version: number;
  readonly calculation_kind: "histogram_binning" | "tukey_box" | "violin_kde" | "density_kde" | "ecdf" | "summary_error" | "percent_stack" | "matrix_projection" | "confusion_count";
  readonly content_hash: string;
}

export type PlotPatchContract = SetAxisRangePatch | SetAxisScalePatch | SetAxisLabelPatch | SetSeriesStylePatch | SetCategoryColorPatch | MoveLegendPatch | SetLegendVisibilityPatch | AddAnnotationPatch | UpdateAnnotationPatch | RemoveAnnotationPatch | ApplyPublicationProfilePatch | SetCanvasSizePatch | SetBatchAxisPolicyPatch

export type PlotProvenance = {
  readonly origin: "manual" | "agent_plan";
  readonly parent_plot_ref?: PlotSpecRef | null;
  readonly plan_id?: string | null;
  readonly user_instruction_hash?: string | null;
  readonly engine_build_hash: string;
}

export type PlotSpec = {
  readonly schema_version?: "1.0";
  readonly plot_id: string;
  readonly plot_version: number;
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61";
  readonly family: XYFamily | CategoricalFamily | DistributionFamily | MatrixFamily | SurvivalFamily | DoseResponseFamily | ForestFamily | FacetFamily;
  readonly prepared_data_refs: ReadonlyArray<PreparedDatasetRef>;
  readonly precomputed_data_refs?: ReadonlyArray<PrecomputedDataRef>;
  readonly plot_calculation_refs?: ReadonlyArray<PlotCalculationResultRef>;
  readonly scales: ReadonlyArray<ScaleSpec>;
  readonly axes: ReadonlyArray<AxisSpec>;
  readonly series: ReadonlyArray<SeriesSpec>;
  readonly annotations?: ReadonlyArray<AnnotationSpec>;
  readonly style_sources: ReadonlyArray<StyleSourceRef>;
  readonly resolved_style: ResolvedStyleSnapshot;
  readonly publication_profile: PublicationProfileSnapshot;
  readonly provenance: PlotProvenance;
}

export type PlotSpecRef = {
  readonly plot_id: string;
  readonly plot_version: number;
  readonly content_hash: string;
}

export type PrecomputedDataRef = {
  readonly precomputed_id: string;
  readonly precomputed_version: number;
  readonly precomputed_kind: "curve" | "band" | "matrix" | "matrix_grid" | "step_curve" | "risk_table" | "parameter_table" | "spectrum" | "peak_labels" | "complex_curve" | "effect_interval";
  readonly content_hash: string;
  readonly data_ref_hash: string;
  readonly field_ids: ReadonlyArray<string>;
  readonly provenance?: "user_provided_precomputed";
}

export type PrecomputedSeriesData = {
  readonly kind?: "precomputed";
  readonly precomputed_data_ref: PrecomputedDataRef;
  readonly role_fields: ReadonlyArray<string>;
}

export type PreparationSpecContract = SelectFieldsSpec | ProjectStructureSpec | IsomorphicConcatSpec | ProjectMetadataLabelSpec | ApplyPlotOrderSpec | MaskForPlotSpec

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

export type PreparedSeriesData = {
  readonly kind?: "prepared";
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly role_fields: ReadonlyArray<string>;
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

export type PublicationProfileIntent = {
  readonly operation?: "apply_publication_profile";
  readonly target_alias: string;
  readonly profile_alias: string;
}

export type PublicationProfileSnapshot = {
  readonly profile_id: string;
  readonly profile_version: number;
  readonly content_hash: string;
  readonly physical_size: PhysicalSize;
  readonly dpi: number;
  readonly color_space?: "sRGB";
}

export type RemoveAnnotationPatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "remove_annotation";
  readonly annotation_id: string;
}

export type ResolvedAxis = {
  readonly axis_id: string;
  readonly scale: "linear" | "log10" | "datetime" | "categorical";
  readonly minimum?: number | null;
  readonly maximum?: number | null;
  readonly reverse?: boolean;
  readonly ticks?: ReadonlyArray<ResolvedTick>;
  readonly label: SafeRichText;
}

export type ResolvedFont = {
  readonly family: string;
  readonly file_hash: string;
  readonly size: PhysicalLength;
}

export type ResolvedLayer = {
  readonly layer_id: string;
  readonly target_id: string;
  readonly geometry: string;
  readonly data_ref: ContentTableRef;
  readonly field_ids: ReadonlyArray<string>;
  readonly z_order: number;
  readonly color?: ColorValue | null;
  readonly line_width?: PhysicalLength | null;
  readonly marker_size?: PhysicalLength | null;
}

export type ResolvedPanel = {
  readonly panel_id: string;
  readonly left: PhysicalLength;
  readonly top: PhysicalLength;
  readonly width: PhysicalLength;
  readonly height: PhysicalLength;
}

export type ResolvedRenderPlan = {
  readonly schema_version?: "1.0";
  readonly render_plan_id: string;
  readonly render_plan_version: number;
  readonly resolver_version: string;
  readonly source_refs: ReadonlyArray<ObjectVersionRef>;
  readonly source_content_hashes: ReadonlyArray<string>;
  readonly quality_tier: "thumbnail" | "interactive" | "formal";
  readonly canvas: PhysicalSize;
  readonly color_space?: "sRGB";
  readonly panels: ReadonlyArray<ResolvedPanel>;
  readonly axes: ReadonlyArray<ResolvedAxis>;
  readonly layers: ReadonlyArray<ResolvedLayer>;
  readonly fonts: ReadonlyArray<ResolvedFont>;
  readonly data_integrity: DataIntegritySnapshot;
  readonly warnings?: ReadonlyArray<WarningRecord>;
}

export type ResolvedStyleSnapshot = {
  readonly font_family: string;
  readonly font_size: PhysicalLength;
  readonly line_width: PhysicalLength;
  readonly marker_size: PhysicalLength;
  readonly colors: ReadonlyArray<ColorValue>;
}

export type ResolvedTick = {
  readonly value: number;
  readonly label: SafeRichText;
}

export type ResourceRef = {
  readonly resource_id: string;
  readonly resource_kind: "authorized_file" | "authorized_directory" | "temporary_output";
}

export type RowExclusion = {
  readonly row_id: string;
  readonly field_id?: string | null;
  readonly reason: "missing" | "nan" | "positive_inf" | "negative_inf";
}

export type SafeRichText = {
  readonly nodes: ReadonlyArray<SafeTextNode>;
}

export type SafeTextNode = {
  readonly kind: "plain" | "newline" | "sub" | "sup" | "bold" | "italic" | "fraction";
  readonly text?: string;
  readonly denominator?: string | null;
}

export type ScaleSpec = {
  readonly scale_id: string;
  readonly kind: "linear" | "log10" | "datetime" | "categorical";
  readonly axis_range?: AxisRange;
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

export type SemanticFieldSelection = {
  readonly role: string;
  readonly context_field_alias: string;
}

export type SeriesSpec = {
  readonly series_id: string;
  readonly geometry: "line" | "symbol" | "error_bar" | "band" | "area" | "bar" | "strip" | "box" | "violin" | "histogram" | "density" | "step" | "heatmap" | "contour" | "risk_table" | "interval" | "panel";
  readonly data: PreparedSeriesData | CalculatedSeriesData | PrecomputedSeriesData;
  readonly label?: SafeRichText | null;
}

export type SeriesStyleIntent = {
  readonly operation?: "set_series_style";
  readonly target_alias: string;
  readonly color?: ColorValue | null;
  readonly line_width_pt?: number | null;
  readonly marker_size_pt?: number | null;
}

export type SetAxisLabelPatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_axis_label";
  readonly label: SafeRichText;
}

export type SetAxisRangePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_axis_range";
  readonly minimum: number;
  readonly maximum: number;
}

export type SetAxisScalePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_axis_scale";
  readonly scale: "linear" | "log10" | "datetime" | "categorical";
}

export type SetBatchAxisPolicyPatch = {
  readonly schema_version?: "1.0";
  readonly operation?: "set_batch_axis_policy";
  readonly target_id: string;
  readonly expected_batch_version: number;
  readonly axis_policy: "per_plot" | "unified";
}

export type SetCanvasSizePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_canvas_size";
  readonly physical_size: PhysicalSize;
}

export type SetCategoryColorPatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_category_color";
  readonly category: string;
  readonly color: ColorValue;
}

export type SetLegendVisibilityPatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_legend_visibility";
  readonly visible: boolean;
}

export type SetSeriesStylePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_series_style";
  readonly color?: ColorValue | null;
  readonly line_width?: PhysicalLength | null;
  readonly marker_size?: PhysicalLength | null;
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

export type StyleSourceRef = {
  readonly source_kind: "project" | "batch" | "plot" | "publication_profile";
  readonly source_id: string;
  readonly source_version: number;
  readonly content_hash: string;
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

export type SurvivalFamily = {
  readonly kind?: "survival";
  readonly geometry: ReadonlyArray<"step" | "band" | "risk_table">;
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
  readonly schema_version?: "1.0";
  readonly decision_type?: "unsupported";
  readonly target_alias: string;
  readonly category: "v1_scope" | "provider_capability" | "chart_capability";
  readonly explanation: string;
}

export type UpdateAnnotationPatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "update_annotation";
  readonly annotation: AnnotationSpec;
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

export type XYFamily = {
  readonly kind?: "xy";
  readonly geometry: ReadonlyArray<"line" | "symbol" | "error_bar" | "band" | "area">;
}
