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

export type AddAnnotationIntent = {
  readonly operation?: "add_annotation";
  readonly target_alias: string;
  readonly kind: "text" | "reference_line" | "reference_band";
  readonly text?: string | null;
  readonly x?: number | null;
  readonly y?: number | null;
  readonly x2?: number | null;
  readonly y2?: number | null;
  readonly affect_range?: boolean;
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
  readonly x2?: number | null;
  readonly y2?: number | null;
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
  readonly minimum?: number | null;
  readonly maximum?: number | null;
}

export type AxisReverseIntent = {
  readonly operation?: "set_axis_reverse";
  readonly target_alias: string;
  readonly reverse: boolean;
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

export type AxisTickSpec = {
  readonly major_interval?: number | null;
  readonly number_format?: "auto" | "fixed" | "scientific";
  readonly decimal_places?: number;
}

export type AxisTicksIntent = {
  readonly operation?: "set_axis_ticks";
  readonly target_alias: string;
  readonly major_interval?: number | null;
  readonly number_format?: "auto" | "fixed" | "scientific";
  readonly decimal_places?: number;
}

export type BarAreaEditSpec = {
  readonly fill_color?: ColorValue | null;
  readonly edge_color?: ColorValue | null;
  readonly edge_width?: PhysicalLength;
  readonly width_ratio?: number;
  readonly alpha?: number;
}

export type BarAreaStyleIntent = {
  readonly operation?: "set_bar_area_style";
  readonly target_alias: string;
  readonly style: BarAreaEditSpec;
}

export type BatchExecutionSignature = {
  readonly dataset_signature: DatasetSignature;
  readonly field_mapping_hash: string;
  readonly preparation_spec_hash: string;
  readonly plot_calculation_spec_hash?: string | null;
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61" | "X01" | "X02" | "X03" | "X05" | "X07" | "X09" | "X11" | "X12" | "X13" | "X15" | "X16" | "X17" | "X18" | "X19" | "X23" | "X24" | "X35" | "X36" | "X37" | "X38" | "S07";
  readonly plot_template_hash: string;
  readonly style_hash: string;
  readonly content_hash: string;
}

export type BatchItemState = {
  readonly item_id: string;
  readonly state: "pending" | "queued" | "preparing" | "running" | "committing" | "succeeded" | "failed" | "cancelled";
  readonly error_code?: string | null;
  readonly plot_version_ref?: PlotSpecRef | null;
  readonly review_state?: "unconfirmed" | "confirmed" | "excluded";
}

export type BatchPlotOverride = {
  readonly item_id: string;
  readonly prepared_dataset_ref: PreparedDatasetRef;
  readonly patches?: ReadonlyArray<SetPlotTitlePatch | SetAxisRangePatch | SetAxisScalePatch | SetAxisLabelPatch | SetAxisReversePatch | SetAxisTicksPatch | SetFontSizePatch | SetBarAreaStylePatch | SetUncertaintyStylePatch | SetColorbarStylePatch | SetDualYAxisStylePatch | SetFacetStylePatch | SetYOffsetStylePatch | SetChartParametersPatch | SetSeriesStylePatch | SetPalettePatch | SetCategoryColorPatch | MoveLegendPatch | SetLegendVisibilityPatch | AddAnnotationPatch | UpdateAnnotationPatch | RemoveAnnotationPatch | ApplyPublicationProfilePatch | SetCanvasSizePatch | SetBatchAxisPolicyPatch>;
}

export type BatchSpec = {
  readonly schema_version?: "1.0";
  readonly batch_id: string;
  readonly batch_version: number;
  readonly dataset_signature: DatasetSignature;
  readonly execution_signature: BatchExecutionSignature;
  readonly dataset_version_refs: ReadonlyArray<PreparedDatasetRef>;
  readonly shared_field_mapping: FieldMappingRef;
  readonly shared_preparation: PreparationSpecRef;
  readonly shared_plot_calculation?: PlotCalculationSpecRef | null;
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

export type CategoryColorIntent = {
  readonly operation?: "set_category_color";
  readonly target_alias: string;
  readonly category: string;
  readonly color: ColorValue;
}

export type ChartCapabilities = {
  readonly capability_version: string;
  readonly allowed_chart_type_ids?: ReadonlyArray<"K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61" | "X01" | "X02" | "X03" | "X05" | "X07" | "X09" | "X11" | "X12" | "X13" | "X15" | "X16" | "X17" | "X18" | "X19" | "X23" | "X24" | "X35" | "X36" | "X37" | "X38" | "S07">;
  readonly allowed_action_types: ReadonlyArray<"create_plot" | "patch_plot" | "create_batch" | "patch_batch" | "create_figure" | "patch_figure" | "export_artifact">;
  readonly allowed_patch_operations?: ReadonlyArray<"set_plot_title" | "set_axis_range" | "set_axis_scale" | "set_axis_label" | "set_axis_reverse" | "set_axis_ticks" | "set_font_size" | "set_bar_area_style" | "set_uncertainty_style" | "set_colorbar_style" | "set_dual_y_style" | "set_facet_style" | "set_y_offset_style" | "set_chart_parameters" | "set_series_style" | "set_category_color" | "set_palette" | "set_legend_visibility" | "move_legend" | "apply_publication_profile" | "set_canvas_size" | "add_annotation">;
  readonly chart_edit_capabilities?: ReadonlyArray<ChartEditCapabilities>;
  readonly export_formats?: ReadonlyArray<"png" | "svg" | "opju">;
  readonly limitation_ids?: ReadonlyArray<string>;
}

export type ChartEditCapabilities = {
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61" | "X01" | "X02" | "X03" | "X05" | "X07" | "X09" | "X11" | "X12" | "X13" | "X15" | "X16" | "X17" | "X18" | "X19" | "X23" | "X24" | "X35" | "X36" | "X37" | "X38" | "S07";
  readonly allowed_patch_operations: ReadonlyArray<"set_plot_title" | "set_axis_range" | "set_axis_scale" | "set_axis_label" | "set_axis_reverse" | "set_axis_ticks" | "set_font_size" | "set_bar_area_style" | "set_uncertainty_style" | "set_colorbar_style" | "set_dual_y_style" | "set_facet_style" | "set_y_offset_style" | "set_chart_parameters" | "set_series_style" | "set_category_color" | "set_palette" | "set_legend_visibility" | "move_legend" | "apply_publication_profile" | "set_canvas_size" | "add_annotation">;
}

export type ChartParameterEditSpec = {
  readonly step_where?: "pre" | "mid" | "post";
  readonly lollipop_baseline?: number;
  readonly volcano_absolute_log2_fold_change?: number;
  readonly volcano_pvalue?: number;
  readonly pareto_reference_percent?: number;
}

export type ChartParametersIntent = {
  readonly operation?: "set_chart_parameters";
  readonly target_alias: string;
  readonly parameters: ChartParameterEditSpec;
}

export type ChartRegistration = {
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61" | "X01" | "X02" | "X03" | "X05" | "X07" | "X09" | "X11" | "X12" | "X13" | "X15" | "X16" | "X17" | "X18" | "X19" | "X23" | "X24" | "X35" | "X36" | "X37" | "X38" | "S07";
  readonly english_name: string;
  readonly family: "xy" | "categorical" | "distribution" | "matrix" | "survival" | "dose_response" | "forest" | "facet" | "special";
  readonly geometries: ReadonlyArray<"line" | "symbol" | "error_bar" | "band" | "area" | "bar" | "strip" | "box" | "violin" | "histogram" | "density" | "step" | "heatmap" | "contour" | "risk_table" | "interval" | "panel" | "lollipop" | "dumbbell" | "beeswarm" | "ridgeline" | "floating_bar" | "bridge" | "bullet" | "pyramid" | "scatter_matrix" | "density2d" | "marginal" | "probability" | "agreement" | "dual_axis" | "y_offset" | "volcano">;
  readonly required_roles: ReadonlyArray<string>;
  readonly optional_roles?: ReadonlyArray<string>;
  readonly required_calculations?: ReadonlyArray<"histogram_binning" | "tukey_box" | "violin_kde" | "density_kde" | "ecdf" | "summary_error" | "percent_stack" | "matrix_projection" | "confusion_count">;
  readonly allowed_calculations?: ReadonlyArray<"histogram_binning" | "tukey_box" | "violin_kde" | "density_kde" | "ecdf" | "summary_error" | "percent_stack" | "matrix_projection" | "confusion_count">;
  readonly required_precomputed?: ReadonlyArray<"curve" | "band" | "matrix" | "matrix_grid" | "step_curve" | "risk_table" | "parameter_table" | "spectrum" | "peak_labels" | "complex_curve" | "effect_interval">;
  readonly exports?: ExportCapabilities;
  readonly admission?: "product" | "internal_only";
  readonly visual_evidence?: "origin_reference" | "synthetic_visual" | "unqualified";
  readonly edit_capabilities?: ReadonlyArray<"plot_title" | "axis_label" | "axis_range" | "axis_scale" | "axis_ticks" | "font" | "legend_visibility" | "legend_position" | "canvas_size" | "publication_profile" | "safe_annotation" | "series_color" | "line_width" | "line_style" | "marker_size" | "symbol_shape" | "symbol_interior" | "palette" | "bar_fill" | "bar_edge" | "bar_width" | "bar_gap" | "error_style" | "band_style" | "colorbar" | "dual_y_style" | "panel_style" | "y_offset" | "chart_parameters">;
  readonly unsupported_edit_capabilities?: ReadonlyArray<"plot_title" | "axis_label" | "axis_range" | "axis_scale" | "axis_ticks" | "font" | "legend_visibility" | "legend_position" | "canvas_size" | "publication_profile" | "safe_annotation" | "series_color" | "line_width" | "line_style" | "marker_size" | "symbol_shape" | "symbol_interior" | "palette" | "bar_fill" | "bar_edge" | "bar_width" | "bar_gap" | "error_style" | "band_style" | "colorbar" | "dual_y_style" | "panel_style" | "y_offset" | "chart_parameters">;
}

export type ChartRegistry = {
  readonly schema_version?: "1.0";
  readonly charts: ReadonlyArray<ChartRegistration>;
}

export type ColorValue = {
  readonly value: string;
}

export type ColorbarEditSpec = {
  readonly visible?: boolean;
  readonly title?: SafeRichText | null;
  readonly minimum?: number | null;
  readonly maximum?: number | null;
  readonly levels?: number;
}

export type ColorbarStyleIntent = {
  readonly operation?: "set_colorbar_style";
  readonly target_alias: string;
  readonly style: ColorbarEditSpec;
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

export type ContextEnvelopeContract = ContextEnvelope

export type ContextField = {
  readonly field_alias: string;
  readonly field_id: string;
  readonly name: string;
  readonly logical_type: "numeric" | "categorical" | "datetime" | "boolean" | "text";
  readonly unit_text?: string;
  readonly semantic_role?: string | null;
  readonly summary?: ContextFieldSummary | null;
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
  readonly object_type: "source_dataset" | "prepared_dataset" | "plot" | "batch" | "figure" | "export" | "project";
  readonly content_hash?: string | null;
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

export type CreateBatchAction = {
  readonly action_id: string;
  readonly depends_on?: ReadonlyArray<string>;
  readonly action_type?: "create_batch";
  readonly target_alias: string;
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61" | "X01" | "X02" | "X03" | "X05" | "X07" | "X09" | "X11" | "X12" | "X13" | "X15" | "X16" | "X17" | "X18" | "X19" | "X23" | "X24" | "X35" | "X36" | "X37" | "X38" | "S07";
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
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61" | "X01" | "X02" | "X03" | "X05" | "X07" | "X09" | "X11" | "X12" | "X13" | "X15" | "X16" | "X17" | "X18" | "X19" | "X23" | "X24" | "X35" | "X36" | "X37" | "X38" | "S07";
  readonly field_selections: ReadonlyArray<SemanticFieldSelection>;
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

export type DataRequest = {
  readonly dataset_alias: string;
  readonly expected_version: number;
  readonly field_aliases: ReadonlyArray<string>;
  readonly requested_categories: ReadonlyArray<"field_metadata" | "statistics" | "sample">;
  readonly estimated_field_count: number;
  readonly estimated_row_count: number;
  readonly estimated_scalar_count: number;
  readonly purpose: string;
  readonly default_context_insufficient_reason: string;
  readonly smaller_scope_possible: boolean;
  readonly authorization_scope: "this_run" | "this_conversation_similar";
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

export type DualYAxisEditSpec = {
  readonly left_color?: ColorValue | null;
  readonly right_color?: ColorValue | null;
  readonly axis_width?: PhysicalLength;
}

export type DualYAxisStyleIntent = {
  readonly operation?: "set_dual_y_style";
  readonly target_alias: string;
  readonly style: DualYAxisEditSpec;
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

export type FacetEditSpec = {
  readonly order?: ReadonlyArray<string>;
  readonly labels?: ReadonlyArray<FacetLabelEdit>;
  readonly gap?: PhysicalLength;
  readonly shared_x?: boolean;
  readonly shared_y?: boolean;
  readonly common_legend?: boolean;
}

export type FacetFamily = {
  readonly kind?: "facet";
  readonly geometry: ReadonlyArray<"panel">;
}

export type FacetLabelEdit = {
  readonly value: string;
  readonly label: string;
}

export type FacetStyleIntent = {
  readonly operation?: "set_facet_style";
  readonly target_alias: string;
  readonly style: FacetEditSpec;
}

export type FieldMapping = {
  readonly schema_version?: "1.0";
  readonly field_mapping_id: string;
  readonly mapping_version: number;
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61" | "X01" | "X02" | "X03" | "X05" | "X07" | "X09" | "X11" | "X12" | "X13" | "X15" | "X16" | "X17" | "X18" | "X19" | "X23" | "X24" | "X35" | "X36" | "X37" | "X38" | "S07";
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
  readonly layout: "1x2" | "1x3" | "1x4" | "2x1" | "2x2" | "2x3" | "3x1";
  readonly panels: ReadonlyArray<FigurePanel>;
  readonly alignment?: "independent" | "align_x" | "align_y" | "align_both";
  readonly axis_policy?: "independent" | "shared_x" | "shared_y" | "shared_both";
  readonly common_legend: boolean;
  readonly physical_size: PhysicalSize;
  readonly publication_profile: PublicationProfileSnapshot;
  readonly parent_figure_version?: number | null;
}

export type FontSizeIntent = {
  readonly operation?: "set_font_size";
  readonly target_alias: string;
  readonly size_pt: number;
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

export type LegendSpec = {
  readonly visible?: boolean | null;
  readonly placement?: "inside" | "outside_right" | "outside_bottom";
  readonly anchor_x?: number;
  readonly anchor_y?: number;
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
  readonly questions?: ReadonlyArray<InputQuestion>;
  readonly data_request?: DataRequest | null;
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

export type NonFiniteSampleValue = {
  readonly kind?: "nonfinite";
  readonly value: "nan" | "positive_inf" | "negative_inf";
}

export type ObjectVersionRef = {
  readonly object_id: string;
  readonly expected_version: number;
}

export type OriginAxisPlan = {
  readonly axis_id: string;
  readonly orientation: "x" | "y";
  readonly position?: "bottom" | "top" | "left" | "right" | "none";
  readonly scale: "linear" | "log10" | "datetime" | "categorical";
  readonly minimum: number;
  readonly maximum: number;
  readonly reverse?: boolean;
  readonly ticks: ReadonlyArray<OriginTickPlan>;
  readonly title?: string;
  readonly color?: ColorValue;
  readonly line_width_pt?: number;
  readonly cross_at?: number | null;
}

export type OriginColumnPlan = {
  readonly field_id: string;
  readonly role: string;
  readonly designation: "X" | "Y" | "Z" | "XError" | "YError" | "Label" | "Group" | "None";
  readonly logical_type: "numeric" | "categorical" | "datetime" | "text";
  readonly long_name: string;
  readonly units?: string;
  readonly comments?: string;
  readonly values: ReadonlyArray<OriginScalar>;
}

export type OriginDataObject = {
  readonly object_id: string;
  readonly object_kind: "worksheet" | "matrixbook";
  readonly folder: "Data" | "Analysis";
  readonly internal_name: string;
  readonly long_name: string;
  readonly data_chain: "direct" | "fixed_plot_calculation" | "user_provided_precomputed";
  readonly data_ref: ContentTableRef;
  readonly columns?: ReadonlyArray<OriginColumnPlan>;
  readonly matrix?: OriginMatrixPlan | null;
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
  readonly manifest: OriginManifestPlan;
  readonly validation?: OriginValidationPlan;
}

export type OriginGraphObject = {
  readonly graph_id: string;
  readonly folder?: "Graphs";
  readonly internal_name: string;
  readonly long_name: string;
  readonly page_width_mm: number;
  readonly page_height_mm: number;
  readonly font_family: string;
  readonly font_size_pt: number;
  readonly title?: string;
  readonly legend_visible: boolean;
  readonly legend_anchor_x?: number;
  readonly legend_anchor_y?: number;
  readonly layers: ReadonlyArray<OriginLayerPlan>;
  readonly data_object_ids: ReadonlyArray<string>;
  readonly annotations?: ReadonlyArray<ResolvedAnnotation>;
  readonly colorbar?: ResolvedColorbar;
}

export type OriginLayerPlan = {
  readonly layer_id: string;
  readonly panel_id: string;
  readonly left_mm: number;
  readonly top_mm: number;
  readonly width_mm: number;
  readonly height_mm: number;
  readonly axes: ReadonlyArray<OriginAxisPlan>;
  readonly plots: ReadonlyArray<OriginPlotPlan>;
  readonly label?: string;
}

export type OriginManifestPlan = {
  readonly chart_type_ids: ReadonlyArray<"K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61" | "X01" | "X02" | "X03" | "X05" | "X07" | "X09" | "X11" | "X12" | "X13" | "X15" | "X16" | "X17" | "X18" | "X19" | "X23" | "X24" | "X35" | "X36" | "X37" | "X38" | "S07">;
  readonly target_scope: "current_plot" | "selected_plots" | "batch" | "figure";
  readonly object_map: ReadonlyArray<OriginObjectMapEntry>;
  readonly render_plan_hashes: ReadonlyArray<string>;
  readonly data_chains: ReadonlyArray<"direct" | "fixed_plot_calculation" | "user_provided_precomputed">;
  readonly resolver_versions: ReadonlyArray<string>;
  readonly raw_data_triggers_plotagent_recalculation?: false;
  readonly external_links?: false;
  readonly known_differences?: ReadonlyArray<string>;
}

export type OriginMatrixPlan = {
  readonly row_count: number;
  readonly column_count: number;
  readonly x_coordinates: ReadonlyArray<number>;
  readonly y_coordinates: ReadonlyArray<number>;
  readonly x_labels?: ReadonlyArray<string>;
  readonly y_labels?: ReadonlyArray<string>;
  readonly values: ReadonlyArray<ReadonlyArray<number | null>>;
  readonly units?: string;
}

export type OriginObjectMapEntry = {
  readonly plotagent_object_id: string;
  readonly origin_object_ref: string;
}

export type OriginPlotPlan = {
  readonly plot_id: string;
  readonly source_layer_id: string;
  readonly native_kind: "line" | "line_symbol" | "scatter" | "bubble" | "error_bar" | "band" | "area" | "bar" | "grouped_bar" | "stacked_bar" | "floating_bar" | "lollipop" | "percent_bar" | "horizontal_bar" | "strip" | "box" | "violin" | "histogram" | "density" | "step" | "heatmap" | "contour" | "survival_step" | "survival_band" | "risk_table" | "forest_interval" | "forest_symbol" | "spectrum" | "nyquist" | "facet_line";
  readonly data_object_id: string;
  readonly role_columns: ReadonlyArray<OriginRoleColumn>;
  readonly z_order: number;
  readonly label?: string;
  readonly color?: ColorValue | null;
  readonly palette?: ReadonlyArray<ColorValue>;
  readonly levels?: ReadonlyArray<number>;
  readonly line_width_pt?: number | null;
  readonly marker_size_pt?: number | null;
  readonly line_style?: "solid" | "dashed" | "dotted" | "dash_dot";
  readonly symbol?: SymbolStyle;
  readonly palette_spec?: ResolvedPalette | null;
  readonly alpha?: number;
  readonly fill_color?: ColorValue | null;
  readonly edge_color?: ColorValue | null;
  readonly edge_width_pt?: number | null;
  readonly width_ratio?: number;
  readonly uncertainty_color?: ColorValue | null;
  readonly uncertainty_line_width_pt?: number | null;
  readonly cap_size_pt?: number | null;
  readonly band_alpha?: number;
  readonly step_where?: "pre" | "mid" | "post";
}

export type OriginRoleColumn = {
  readonly role: string;
  readonly field_id: string;
}

export type OriginScalar = string | number | boolean | null

export type OriginTemplateRef = {
  readonly template_resource: ResourceRef;
  readonly template_hash: string;
  readonly signature_hash: string;
}

export type OriginTickPlan = {
  readonly value: number;
  readonly label: string;
}

export type OriginValidationPlan = {
  readonly live_structural_validation?: true;
  readonly fresh_reopen_validation?: true;
  readonly require_no_external_links?: true;
  readonly require_atomic_publish?: true;
}

export type PaletteIntent = {
  readonly operation?: "set_palette";
  readonly target_alias: string;
  readonly palette_id: "ColorBlindSafe8" | "ColorBlindSafe15" | "BlueOrange" | "OrangeNavy" | "RedPurple" | "Viridis" | "Plasma" | "Inferno" | "Magma" | "GreyBlue" | "YellowBlue" | "YellowGreen" | "YellowPurple" | "Fire" | "Rainbow_Modified" | "GrayScale";
  readonly reverse?: boolean;
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
  readonly patches: ReadonlyArray<PlotTitleIntent | AxisRangeIntent | AxisScaleIntent | AxisLabelIntent | AxisReverseIntent | AxisTicksIntent | FontSizeIntent | BarAreaStyleIntent | UncertaintyStyleIntent | ColorbarStyleIntent | DualYAxisStyleIntent | FacetStyleIntent | YOffsetStyleIntent | ChartParametersIntent | SeriesStyleIntent | CategoryColorIntent | PaletteIntent | LegendVisibilityIntent | LegendPlacementIntent | PublicationProfileIntent | CanvasSizeIntent | AddAnnotationIntent>;
}

export type PatchTransaction = {
  readonly schema_version?: "1.0";
  readonly transaction_id: string;
  readonly project_id: string;
  readonly expected_versions: ReadonlyArray<ObjectVersionRef>;
  readonly patches: ReadonlyArray<SetPlotTitlePatch | SetAxisRangePatch | SetAxisScalePatch | SetAxisLabelPatch | SetAxisReversePatch | SetAxisTicksPatch | SetFontSizePatch | SetBarAreaStylePatch | SetUncertaintyStylePatch | SetColorbarStylePatch | SetDualYAxisStylePatch | SetFacetStylePatch | SetYOffsetStylePatch | SetChartParametersPatch | SetSeriesStylePatch | SetPalettePatch | SetCategoryColorPatch | MoveLegendPatch | SetLegendVisibilityPatch | AddAnnotationPatch | UpdateAnnotationPatch | RemoveAnnotationPatch | ApplyPublicationProfilePatch | SetCanvasSizePatch | SetBatchAxisPolicyPatch>;
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

export type PlotPatchContract = SetPlotTitlePatch | SetAxisRangePatch | SetAxisScalePatch | SetAxisLabelPatch | SetAxisReversePatch | SetAxisTicksPatch | SetFontSizePatch | SetBarAreaStylePatch | SetUncertaintyStylePatch | SetColorbarStylePatch | SetDualYAxisStylePatch | SetFacetStylePatch | SetYOffsetStylePatch | SetChartParametersPatch | SetSeriesStylePatch | SetPalettePatch | SetCategoryColorPatch | MoveLegendPatch | SetLegendVisibilityPatch | AddAnnotationPatch | UpdateAnnotationPatch | RemoveAnnotationPatch | ApplyPublicationProfilePatch | SetCanvasSizePatch | SetBatchAxisPolicyPatch

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
  readonly chart_type_id: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61" | "X01" | "X02" | "X03" | "X05" | "X07" | "X09" | "X11" | "X12" | "X13" | "X15" | "X16" | "X17" | "X18" | "X19" | "X23" | "X24" | "X35" | "X36" | "X37" | "X38" | "S07";
  readonly title?: SafeRichText | null;
  readonly family: XYFamily | CategoricalFamily | DistributionFamily | MatrixFamily | SurvivalFamily | DoseResponseFamily | ForestFamily | FacetFamily | SpecialFamily;
  readonly prepared_data_refs: ReadonlyArray<PreparedDatasetRef>;
  readonly precomputed_data_refs?: ReadonlyArray<PrecomputedDataRef>;
  readonly plot_calculation_refs?: ReadonlyArray<PlotCalculationResultRef>;
  readonly scales: ReadonlyArray<ScaleSpec>;
  readonly axes: ReadonlyArray<AxisSpec>;
  readonly series: ReadonlyArray<SeriesSpec>;
  readonly legend?: LegendSpec;
  readonly annotations?: ReadonlyArray<AnnotationSpec>;
  readonly specialist?: SpecialistEditSpec;
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

export type PlotTitleIntent = {
  readonly operation?: "set_plot_title";
  readonly target_alias: string;
  readonly title?: string | null;
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

export type ResolvedAnnotation = {
  readonly annotation_id: string;
  readonly panel_id?: string;
  readonly kind: "text" | "arrow" | "line" | "rectangle" | "reference_line" | "reference_band" | "peak_label" | "significance_bracket" | "panel_label";
  readonly text?: SafeRichText | null;
  readonly color?: ColorValue | null;
  readonly x?: number | null;
  readonly y?: number | null;
  readonly x2?: number | null;
  readonly y2?: number | null;
  readonly affect_range?: boolean;
}

export type ResolvedAxis = {
  readonly axis_id: string;
  readonly panel_id?: string;
  readonly orientation?: "x" | "y" | "color";
  readonly position?: "bottom" | "top" | "left" | "right" | "none";
  readonly scale: "linear" | "log10" | "datetime" | "categorical";
  readonly minimum?: number | null;
  readonly maximum?: number | null;
  readonly reverse?: boolean;
  readonly ticks?: ReadonlyArray<ResolvedTick>;
  readonly exponent?: number;
  readonly precision?: number;
  readonly label: SafeRichText;
  readonly color?: ColorValue;
  readonly line_width?: PhysicalLength;
  readonly cross_at?: number | null;
}

export type ResolvedColorbar = {
  readonly visible?: boolean;
  readonly title?: SafeRichText | null;
  readonly minimum?: number | null;
  readonly maximum?: number | null;
  readonly levels?: number;
}

export type ResolvedFieldBinding = {
  readonly role: string;
  readonly field_id: string;
}

export type ResolvedFont = {
  readonly family: string;
  readonly file_hash: string;
  readonly size: PhysicalLength;
}

export type ResolvedLayer = {
  readonly layer_id: string;
  readonly target_id: string;
  readonly panel_id?: string;
  readonly geometry: string;
  readonly data_source_kind?: "direct" | "fixed" | "user_precomputed" | "panel_plan";
  readonly data_ref: ContentTableRef;
  readonly field_ids: ReadonlyArray<string>;
  readonly field_bindings?: ReadonlyArray<ResolvedFieldBinding>;
  readonly full_row_count?: number;
  readonly displayed_row_count?: number;
  readonly z_order: number;
  readonly label?: SafeRichText | null;
  readonly color?: ColorValue | null;
  readonly palette?: ReadonlyArray<ColorValue>;
  readonly levels?: ReadonlyArray<number>;
  readonly color_minimum?: number | null;
  readonly color_maximum?: number | null;
  readonly line_width?: PhysicalLength | null;
  readonly marker_size?: PhysicalLength | null;
  readonly line_style?: "solid" | "dashed" | "dotted" | "dash_dot";
  readonly symbol?: SymbolStyle;
  readonly palette_spec?: ResolvedPalette | null;
  readonly fill_color?: ColorValue | null;
  readonly edge_color?: ColorValue | null;
  readonly edge_width?: PhysicalLength | null;
  readonly width_ratio?: number;
  readonly alpha?: number;
  readonly uncertainty_color?: ColorValue | null;
  readonly uncertainty_line_width?: PhysicalLength | null;
  readonly cap_size?: PhysicalLength | null;
  readonly band_alpha?: number;
  readonly step_where?: "pre" | "mid" | "post";
}

export type ResolvedLegend = {
  readonly visible?: boolean;
  readonly placement?: "inside" | "outside_right" | "outside_bottom";
  readonly anchor_x?: number;
  readonly anchor_y?: number;
  readonly common?: boolean;
}

export type ResolvedPalette = {
  readonly palette_id: "ColorBlindSafe8" | "ColorBlindSafe15" | "BlueOrange" | "OrangeNavy" | "RedPurple" | "Viridis" | "Plasma" | "Inferno" | "Magma" | "GreyBlue" | "YellowBlue" | "YellowGreen" | "YellowPurple" | "Fire" | "Rainbow_Modified" | "GrayScale";
  readonly origin_source_name: string;
  readonly origin_asset_kind: "color_list" | "palette";
  readonly kind: "qualitative" | "sequential" | "diverging" | "special" | "grayscale";
  readonly colors: ReadonlyArray<ColorValue>;
  readonly reverse?: boolean;
  readonly source_version?: "Origin2024 SR1 10.10.178";
  readonly source_hash: string;
  readonly resolved_rgb_hash: string;
}

export type ResolvedPanel = {
  readonly panel_id: string;
  readonly left: PhysicalLength;
  readonly top: PhysicalLength;
  readonly width: PhysicalLength;
  readonly height: PhysicalLength;
  readonly label?: SafeRichText | null;
}

export type ResolvedRenderPlan = {
  readonly schema_version?: "1.0";
  readonly render_plan_id: string;
  readonly render_plan_version: number;
  readonly chart_type_id?: "K01" | "K02" | "K03" | "K04" | "K05" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K16" | "K17" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "K25" | "S01" | "S05" | "S21" | "S25" | "S31" | "S34" | "S61" | "X01" | "X02" | "X03" | "X05" | "X07" | "X09" | "X11" | "X12" | "X13" | "X15" | "X16" | "X17" | "X18" | "X19" | "X23" | "X24" | "X35" | "X36" | "X37" | "X38" | "S07" | null;
  readonly resolver_version: string;
  readonly source_refs: ReadonlyArray<ObjectVersionRef>;
  readonly source_content_hashes: ReadonlyArray<string>;
  readonly quality_tier: "thumbnail" | "interactive" | "formal";
  readonly canvas: PhysicalSize;
  readonly dpi?: number;
  readonly background?: ColorValue;
  readonly title?: SafeRichText | null;
  readonly color_space?: "sRGB";
  readonly svg_text_mode?: "text_to_path" | "editable_text";
  readonly panels: ReadonlyArray<ResolvedPanel>;
  readonly axes: ReadonlyArray<ResolvedAxis>;
  readonly layers: ReadonlyArray<ResolvedLayer>;
  readonly fonts: ReadonlyArray<ResolvedFont>;
  readonly legend?: ResolvedLegend;
  readonly colorbar?: ResolvedColorbar;
  readonly annotations?: ReadonlyArray<ResolvedAnnotation>;
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
  readonly ticks?: AxisTickSpec;
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

export type SemanticFieldSelection = {
  readonly role: string;
  readonly context_field_alias: string;
}

export type SeriesSpec = {
  readonly series_id: string;
  readonly geometry: "line" | "symbol" | "error_bar" | "band" | "area" | "bar" | "strip" | "box" | "violin" | "histogram" | "density" | "step" | "heatmap" | "contour" | "risk_table" | "interval" | "panel" | "lollipop" | "dumbbell" | "beeswarm" | "ridgeline" | "floating_bar" | "bridge" | "bullet" | "pyramid" | "scatter_matrix" | "density2d" | "marginal" | "probability" | "agreement" | "dual_axis" | "y_offset" | "volcano";
  readonly data: PreparedSeriesData | CalculatedSeriesData | PrecomputedSeriesData;
  readonly label?: SafeRichText | null;
  readonly style?: SeriesStyleSpec;
}

export type SeriesStyleIntent = {
  readonly operation?: "set_series_style";
  readonly target_alias: string;
  readonly color?: ColorValue | null;
  readonly line_width_pt?: number | null;
  readonly marker_size_pt?: number | null;
  readonly line_style?: "solid" | "dashed" | "dotted" | "dash_dot" | null;
  readonly symbol_shape?: "square" | "circle" | "triangle_up" | "triangle_down" | "diamond" | "plus" | "cross" | "triangle_left" | "triangle_right" | "hexagon" | "star" | "pentagon" | null;
  readonly symbol_interior?: "solid" | "open" | "hollow" | null;
}

export type SeriesStyleSpec = {
  readonly color?: ColorValue | null;
  readonly category_colors?: Readonly<Record<string, ColorValue>>;
  readonly line_width?: PhysicalLength | null;
  readonly marker_size?: PhysicalLength | null;
  readonly line_style?: "solid" | "dashed" | "dotted" | "dash_dot";
  readonly symbol?: SymbolStyle;
  readonly palette?: ResolvedPalette | null;
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
  readonly minimum?: number | null;
  readonly maximum?: number | null;
}

export type SetAxisReversePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_axis_reverse";
  readonly reverse: boolean;
}

export type SetAxisScalePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_axis_scale";
  readonly scale: "linear" | "log10" | "datetime" | "categorical";
}

export type SetAxisTicksPatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_axis_ticks";
  readonly ticks: AxisTickSpec;
}

export type SetBarAreaStylePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_bar_area_style";
  readonly style: BarAreaEditSpec;
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

export type SetChartParametersPatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_chart_parameters";
  readonly parameters: ChartParameterEditSpec;
}

export type SetColorbarStylePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_colorbar_style";
  readonly style: ColorbarEditSpec;
}

export type SetDualYAxisStylePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_dual_y_style";
  readonly style: DualYAxisEditSpec;
}

export type SetFacetStylePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_facet_style";
  readonly style: FacetEditSpec;
}

export type SetFontSizePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_font_size";
  readonly size: PhysicalLength;
}

export type SetLegendVisibilityPatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_legend_visibility";
  readonly visible: boolean;
}

export type SetPalettePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_palette";
  readonly palette_id: "ColorBlindSafe8" | "ColorBlindSafe15" | "BlueOrange" | "OrangeNavy" | "RedPurple" | "Viridis" | "Plasma" | "Inferno" | "Magma" | "GreyBlue" | "YellowBlue" | "YellowGreen" | "YellowPurple" | "Fire" | "Rainbow_Modified" | "GrayScale";
  readonly reverse?: boolean;
}

export type SetPlotTitlePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_plot_title";
  readonly title?: SafeRichText | null;
}

export type SetSeriesStylePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_series_style";
  readonly color?: ColorValue | null;
  readonly line_width?: PhysicalLength | null;
  readonly marker_size?: PhysicalLength | null;
  readonly line_style?: "solid" | "dashed" | "dotted" | "dash_dot" | null;
  readonly symbol?: SymbolStyle | null;
}

export type SetUncertaintyStylePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_uncertainty_style";
  readonly style: UncertaintyEditSpec;
}

export type SetYOffsetStylePatch = {
  readonly schema_version?: "1.0";
  readonly target_id: string;
  readonly expected_plot_version: number;
  readonly operation?: "set_y_offset_style";
  readonly style: YOffsetEditSpec;
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

export type SpecialFamily = {
  readonly kind?: "special";
  readonly geometry: ReadonlyArray<"step" | "lollipop" | "dumbbell" | "beeswarm" | "ridgeline" | "floating_bar" | "bridge" | "bullet" | "pyramid" | "scatter_matrix" | "density2d" | "marginal" | "probability" | "agreement" | "dual_axis" | "y_offset" | "volcano">;
}

export type SpecialistEditSpec = {
  readonly bar_area?: BarAreaEditSpec;
  readonly uncertainty?: UncertaintyEditSpec;
  readonly colorbar?: ColorbarEditSpec;
  readonly dual_y?: DualYAxisEditSpec;
  readonly facet?: FacetEditSpec;
  readonly y_offset?: YOffsetEditSpec;
  readonly chart_parameters?: ChartParameterEditSpec;
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

export type SymbolStyle = {
  readonly shape?: "square" | "circle" | "triangle_up" | "triangle_down" | "diamond" | "plus" | "cross" | "triangle_left" | "triangle_right" | "hexagon" | "star" | "pentagon";
  readonly interior?: "solid" | "open" | "hollow";
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

export type UncertaintyEditSpec = {
  readonly color?: ColorValue | null;
  readonly line_width?: PhysicalLength;
  readonly cap_size?: PhysicalLength;
  readonly band_alpha?: number;
}

export type UncertaintyStyleIntent = {
  readonly operation?: "set_uncertainty_style";
  readonly target_alias: string;
  readonly style: UncertaintyEditSpec;
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

export type YOffsetEditSpec = {
  readonly distance?: number | null;
  readonly order?: ReadonlyArray<string>;
}

export type YOffsetStyleIntent = {
  readonly operation?: "set_y_offset_style";
  readonly target_alias: string;
  readonly style: YOffsetEditSpec;
}
