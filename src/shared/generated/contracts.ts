// Generated from schemas/contracts-bundle.schema.json. Do not edit.

export const CONTRACT_SCHEMA_VERSION = "1.0" as const

export type ActivationBudget = {
  readonly max_model_turns?: number;
  readonly max_tool_calls?: number;
  readonly max_disclosed_scalars?: number;
  readonly timeout_ms?: number | null;
}

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

export type AgentActivation = {
  readonly schema_version?: "agent-activation.v2";
  readonly activation_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly reason: "new_task" | "user_answered" | "user_corrected" | "verification_failed" | "external_blocker_cleared" | "resume_after_restart";
  readonly task_state: "created" | "investigating" | "awaiting_input" | "intent_staged" | "awaiting_confirmation" | "executing" | "verifying" | "repairing" | "awaiting_reconfirmation" | "delivering" | "partial" | "blocked" | "unsupported" | "cancelling" | "cancelled" | "rejected" | "failed" | "completed_verified";
  readonly original_instruction: string;
  readonly current_user_message?: string | null;
  readonly confirmed_intent?: IntentRef | null;
  readonly item_states?: ReadonlyArray<readonly [string, "pending" | "staged" | "running" | "succeeded" | "repairable_failed" | "failed" | "blocked" | "cancelled"]>;
  readonly context_refs?: ReadonlyArray<string>;
  readonly domain_knowledge_refs?: ReadonlyArray<string>;
  readonly verification_report_ids?: ReadonlyArray<string>;
  readonly prior_receipt_ids?: ReadonlyArray<string>;
  readonly allowed_tools: ReadonlyArray<string>;
  readonly permission_phase: "p0_read" | "p1_staged" | "p2_confirmed" | "p3_expanded";
  readonly activation_budget: ActivationBudget;
  readonly task_budget: TaskBudgetSnapshot;
  readonly deadline?: string | null;
  readonly created_at: string;
}

export type AgentActivationEvent = {
  readonly event_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly sequence: number;
  readonly occurred_at: string;
  readonly event_type?: "agent_activation";
  readonly activation_id: string;
  readonly phase: "requested" | "started" | "yielded" | "aborted" | "runtime_failed";
  readonly yield_outcome?: "intent_ready" | "needs_input" | "information_ready" | "technical_repair_ready" | "unsupported" | "blocked" | "budget_exhausted" | "cancelled" | "runtime_failed" | null;
}

export type AgentBlocked = {
  readonly outcome?: "blocked";
  readonly activation_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly blocker_code: string;
  readonly message: string;
  readonly resume_condition: string;
  readonly retryable: boolean;
}

export type AgentBudgetExhausted = {
  readonly outcome?: "budget_exhausted";
  readonly activation_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly exhausted_budget: "model_calls" | "model_turns" | "input_tokens" | "output_tokens" | "tool_calls" | "disclosed_scalars" | "origin_sessions" | "repair_attempts" | "wall_time" | "estimated_cost";
  readonly message: string;
}

export type AgentCancelled = {
  readonly outcome?: "cancelled";
  readonly activation_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly message: string;
}

export type AgentContextSnapshot = {
  readonly schema_version?: "agent-context.v2";
  readonly context_snapshot_id: string;
  readonly context_version: number;
  readonly task_id: string;
  readonly task_version: number;
  readonly activation_id: string;
  readonly activation_reason: "new_task" | "user_answered" | "user_corrected" | "verification_failed" | "external_blocker_cleared" | "resume_after_restart";
  readonly task_state: "created" | "investigating" | "awaiting_input" | "intent_staged" | "awaiting_confirmation" | "executing" | "verifying" | "repairing" | "awaiting_reconfirmation" | "delivering" | "partial" | "blocked" | "unsupported" | "cancelling" | "cancelled" | "rejected" | "failed" | "completed_verified";
  readonly checkpoint_id: string;
  readonly checkpoint_hash: string;
  readonly last_event_sequence: number;
  readonly project_id: string;
  readonly project_revision: number;
  readonly original_instruction: string;
  readonly current_user_message?: string | null;
  readonly confirmed_intent?: IntentRef | null;
  readonly item_states?: ReadonlyArray<readonly [string, "pending" | "staged" | "running" | "succeeded" | "repairable_failed" | "failed" | "blocked" | "cancelled"]>;
  readonly verification_report_ids?: ReadonlyArray<string>;
  readonly verification_reports?: ReadonlyArray<VerificationReport>;
  readonly prior_receipt_ids?: ReadonlyArray<string>;
  readonly permission_phase: "p0_read" | "p1_staged" | "p2_confirmed" | "p3_expanded";
  readonly selected_sources?: ReadonlyArray<SourceDatasetRef>;
  readonly selected_plots?: ReadonlyArray<SelectedPlotRef>;
  readonly selected_plot_contexts?: ReadonlyArray<SelectedPlotContext>;
  readonly selected_profile_ids?: ReadonlyArray<"K01" | "K02" | "K03" | "K04" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "S34" | "S61" | "X02" | "X03" | "X05" | "X09" | "X13" | "X23" | "X24" | "X35" | "X36" | "X38" | "X39" | "X40">;
  readonly source_contexts?: ReadonlyArray<UntrustedSourceContext>;
  readonly chart_catalog: ReadonlyArray<ChartCatalogEntry>;
  readonly chart_knowledge?: ReadonlyArray<ChartKnowledgeCard>;
  readonly calculation_contracts?: ReadonlyArray<CalculationContract>;
  readonly tools: ReadonlyArray<ContextToolContract>;
  readonly activation_budget: ActivationBudget;
  readonly task_budget: TaskBudgetSnapshot;
  readonly disclosed_scalars: number;
  readonly data_is_untrusted?: true;
  readonly data_cannot_change_permissions?: true;
  readonly constitution: ReadonlyArray<string>;
  readonly content_hash: string;
}

export type AgentInformationReady = {
  readonly outcome?: "information_ready";
  readonly activation_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly message: string;
}

export type AgentIntentReady = {
  readonly outcome?: "intent_ready";
  readonly activation_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly intent: TaskIntent;
}

export type AgentNeedsInput = {
  readonly outcome?: "needs_input";
  readonly activation_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly questions: ReadonlyArray<InputQuestion>;
}

export type AgentRuntimeFailed = {
  readonly outcome?: "runtime_failed";
  readonly activation_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly error: TaskError;
}

export type AgentTechnicalRepairReady = {
  readonly outcome?: "technical_repair_ready";
  readonly activation_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly proposal: RepairProposal;
}

export type AgentToolError = {
  readonly code: string;
  readonly category: "AGENT_REPAIRABLE" | "USER_INPUT_REQUIRED" | "TRANSIENT" | "UNSUPPORTED" | "FATAL";
  readonly message: string;
  readonly retryable: boolean;
  readonly requires_user: boolean;
  readonly repair_hint?: string | null;
  readonly side_effect_state: "none" | "staged" | "committed" | "unknown";
  readonly diagnostic_id?: string | null;
}

export type AgentToolResult = {
  readonly schema_version?: "agent-tool-result.v2";
  readonly tool_call_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly activation_id: string;
  readonly tool_name: string;
  readonly status: "succeeded" | "failed";
  readonly summary: string;
  readonly payload?: JsonValue | null;
  readonly output_hash?: string | null;
  readonly output_handle?: string | null;
  readonly provenance?: ReadonlyArray<ToolProvenance>;
  readonly verification_report_ids?: ReadonlyArray<string>;
  readonly warnings?: ReadonlyArray<ToolWarning>;
  readonly side_effect: "none" | "staged" | "committed" | "unknown";
  readonly side_effects?: ReadonlyArray<SideEffectReceipt>;
  readonly disclosed_field_count?: number;
  readonly disclosed_row_count?: number;
  readonly disclosed_scalar_count?: number;
  readonly error?: AgentToolError | null;
  readonly started_at: string;
  readonly completed_at: string;
}

export type AgentUnsupported = {
  readonly outcome?: "unsupported";
  readonly activation_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly reason_code: string;
  readonly message: string;
  readonly alternatives?: ReadonlyArray<string>;
}

export type AgentYieldContract = AgentIntentReady | AgentNeedsInput | AgentInformationReady | AgentTechnicalRepairReady | AgentUnsupported | AgentBlocked | AgentBudgetExhausted | AgentCancelled | AgentRuntimeFailed

export type AggregateMetric = {
  readonly operator: "count" | "count_nonmissing" | "sum" | "mean" | "min" | "max" | "median";
  readonly input_field_id?: string | null;
  readonly output_field_id: string;
  readonly output_name: string;
}

export type AggregateOperation = {
  readonly kind?: "aggregate";
  readonly input_handle_id: string;
  readonly group_field_ids?: ReadonlyArray<string>;
  readonly metrics: ReadonlyArray<AggregateMetric>;
}

export type AlignSourcesOnX = {
  readonly operation?: "align_sources_on_x";
  readonly source_aliases: ReadonlyArray<string>;
  readonly x_field_aliases: ReadonlyArray<string>;
  readonly value_field_aliases: ReadonlyArray<string>;
  readonly output_x_field_alias: string;
  readonly output_x_name: string;
  readonly output_series_fields: ReadonlyArray<WorkflowOutputField>;
  readonly numeric_tolerance?: number;
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

export type BucketizeNumeric = {
  readonly operation?: "bucketize_numeric";
  readonly source_alias: string;
  readonly field_alias: string;
  readonly boundaries: ReadonlyArray<number>;
  readonly labels: ReadonlyArray<string>;
  readonly output_field_alias: string;
  readonly output_name: string;
}

export type CalculationContract = {
  readonly schema_version?: "calculation-contract.v1";
  readonly contract_id: string;
  readonly contract_version: number;
  readonly calculation_kind: "histogram_binning" | "tukey_box" | "violin_kde" | "ecdf" | "summary_error" | "percent_stack" | "matrix_projection" | "confusion_count";
  readonly algorithm_id: string;
  readonly algorithm_version: string;
  readonly spec_schema_hash: string;
  readonly input_roles: ReadonlyArray<CalculationInputRole>;
  readonly definition: ReadonlyArray<string>;
  readonly parameters?: ReadonlyArray<CalculationParameter>;
  readonly missing_value_behavior: string;
  readonly boundary_behavior: ReadonlyArray<string>;
  readonly output_fields: ReadonlyArray<string>;
  readonly linked_profile_ids?: ReadonlyArray<"K01" | "K02" | "K03" | "K04" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "S34" | "S61" | "X02" | "X03" | "X05" | "X09" | "X13" | "X23" | "X24" | "X35" | "X36" | "X38" | "X39" | "X40">;
  readonly oracle_ids: ReadonlyArray<string>;
}

export type CalculationInputRole = {
  readonly role: string;
  readonly accepted_types: ReadonlyArray<"numeric" | "categorical" | "datetime" | "boolean" | "text">;
  readonly required?: boolean;
}

export type CalculationParameter = {
  readonly name: string;
  readonly value_type: "enum" | "integer" | "number" | "boolean" | "field" | "field_list";
  readonly default?: string | number | boolean | null;
  readonly constraint: string;
}

export type CalculationTable = {
  readonly field_ids: ReadonlyArray<string>;
  readonly rows: ReadonlyArray<ReadonlyArray<string | boolean | number | null>>;
}

export type ChartCatalogEntry = {
  readonly profile_id: "K01" | "K02" | "K03" | "K04" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "S34" | "S61" | "X02" | "X03" | "X05" | "X09" | "X13" | "X23" | "X24" | "X35" | "X36" | "X38" | "X39" | "X40";
  readonly knowledge_id: string;
  readonly knowledge_version: number;
  readonly knowledge_hash: string;
  readonly display_name_zh: string;
  readonly official_name: string;
  readonly summary: string;
  readonly required_roles: ReadonlyArray<string>;
  readonly optional_roles?: ReadonlyArray<string>;
  readonly repeatable_role_prefixes?: ReadonlyArray<string>;
}

export type ChartEvidenceRef = {
  readonly evidence_id: string;
  readonly title: string;
  readonly official_url: string;
  readonly reviewed_product_version: string;
  readonly evidence_digest: string;
  readonly claim_ids: ReadonlyArray<string>;
}

export type ChartKnowledgeCard = {
  readonly schema_version?: "chart-knowledge.v1";
  readonly knowledge_id: string;
  readonly knowledge_version: number;
  readonly profile_id: "K01" | "K02" | "K03" | "K04" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "S34" | "S61" | "X02" | "X03" | "X05" | "X09" | "X13" | "X23" | "X24" | "X35" | "X36" | "X38" | "X39" | "X40";
  readonly engine_profile: EngineProfile;
  readonly engine_profile_hash: string;
  readonly display_name_zh: string;
  readonly official_name: string;
  readonly user_facing_description: string;
  readonly intended_questions: ReadonlyArray<string>;
  readonly unsuitable_questions: ReadonlyArray<string>;
  readonly source_shapes: ReadonlyArray<"worksheet_xy" | "worksheet_wide" | "worksheet_long_indexed" | "matrix" | "analysis_table">;
  readonly data_requirements: ReadonlyArray<string>;
  readonly row_relations: ReadonlyArray<string>;
  readonly ordering_semantics: ReadonlyArray<string>;
  readonly fixed_scientific_semantics: ReadonlyArray<string>;
  readonly allowed_preparations?: ReadonlyArray<string>;
  readonly forbidden_preparations: ReadonlyArray<string>;
  readonly unsupported_actions?: ReadonlyArray<string>;
  readonly calculation_contract_ids?: ReadonlyArray<string>;
  readonly examples: ReadonlyArray<DomainExample>;
  readonly validation_claims: ReadonlyArray<string>;
  readonly evidence_refs: ReadonlyArray<ChartEvidenceRef>;
}

export type ChartProfileComparison = {
  readonly profile_ids: ReadonlyArray<"K01" | "K02" | "K03" | "K04" | "K06" | "K07" | "K08" | "K09" | "K10" | "K11" | "K12" | "K13" | "K14" | "K15" | "K18" | "K19" | "K20" | "K21" | "K22" | "K24" | "S34" | "S61" | "X02" | "X03" | "X05" | "X09" | "X13" | "X23" | "X24" | "X35" | "X36" | "X38" | "X39" | "X40">;
  readonly entries: ReadonlyArray<ChartCatalogEntry>;
  readonly source_shapes: Readonly<Record<string, ReadonlyArray<"worksheet_xy" | "worksheet_wide" | "worksheet_long_indexed" | "matrix" | "analysis_table">>>;
  readonly fixed_semantics: Readonly<Record<string, ReadonlyArray<string>>>;
  readonly forbidden_preparations: Readonly<Record<string, ReadonlyArray<string>>>;
}

export type CompiledTaskItem = {
  readonly task_kind: "create" | "edit" | "update_data";
  readonly item_id: string;
  readonly plot_alias: string;
  readonly plot_id: string;
  readonly profile_id: string;
  readonly target_plot_id?: string | null;
  readonly target_plot_version?: number | null;
  readonly sources?: ReadonlyArray<WorkflowSource>;
  readonly resolved_fields?: ReadonlyArray<ResolvedWorkflowField>;
  readonly data_operations: ReadonlyArray<SelectFields | FilterRows | SortRows | ExcludeRows | DropEmptyFields | ConvertType | ReshapeLongToWide | ReshapeWideToLong | ConcatenateSources | AlignSourcesOnX | RenameField | DeriveColumn | ConvertUnit | BucketizeNumeric>;
  readonly bindings?: ReadonlyArray<ResolvedFieldBinding>;
  readonly visual_actions: ReadonlyArray<DraftSetTitle | DraftSetAxis | DraftSetSeriesStyle | DraftSetLegend | DraftSetColorMap | DraftSetErrorStyle | DraftSetDataLabels | DraftSetChartParameter | DraftAddAnnotation>;
  readonly depends_on?: ReadonlyArray<string>;
  readonly idempotency_key: string;
}

export type ConcatenateOperation = {
  readonly kind?: "concatenate";
  readonly input_handle_ids: ReadonlyArray<string>;
  readonly source_labels: ReadonlyArray<string>;
  readonly source_label_field_id: string;
  readonly source_label_name?: string;
}

export type ConcatenateSources = {
  readonly operation?: "concatenate_sources";
  readonly source_aliases: ReadonlyArray<string>;
  readonly source_label_field?: string;
  readonly source_labels?: ReadonlyArray<string>;
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

export type ContextToolContract = {
  readonly tool_name: string;
  readonly permission_phase: "p0_read" | "p1_staged" | "p2_confirmed" | "p3_expanded";
  readonly input_schema_hash: string;
  readonly output_schema_hash: string;
  readonly description: string;
  readonly side_effect: "none" | "staged" | "confirmed_write" | "expanded_risk";
}

export type ConvertType = {
  readonly operation?: "convert_type";
  readonly source_alias: string;
  readonly field_alias: string;
  readonly target_type: "numeric" | "categorical" | "datetime" | "boolean" | "text";
  readonly output_field_alias: string;
  readonly output_name: string;
  readonly decimal_separator?: "." | ",";
  readonly thousands_separator?: "," | "." | " " | null;
  readonly datetime_format?: string | null;
  readonly true_values?: ReadonlyArray<string>;
  readonly false_values?: ReadonlyArray<string>;
  readonly case_sensitive?: boolean;
}

export type ConvertTypeOperation = {
  readonly kind?: "convert_type";
  readonly input_handle_id: string;
  readonly field_id: string;
  readonly target_type: "numeric" | "categorical" | "datetime" | "boolean" | "text";
  readonly output_field_id: string;
  readonly output_name: string;
  readonly decimal_separator?: "." | "," | null;
  readonly thousands_separator?: "," | "." | " " | null;
  readonly datetime_format?: string | null;
  readonly true_values?: ReadonlyArray<string>;
  readonly false_values?: ReadonlyArray<string>;
  readonly case_sensitive?: boolean;
}

export type ConvertUnit = {
  readonly operation?: "convert_unit";
  readonly source_alias: string;
  readonly field_alias: string;
  readonly target_unit: string;
  readonly output_field_alias: string;
  readonly output_name: string;
}

export type ConvertUnitOperation = {
  readonly kind?: "convert_unit";
  readonly input_handle_id: string;
  readonly field_id: string;
  readonly target_unit: string;
  readonly output_field_id: string;
  readonly output_name: string;
}

export type CreatePlot = {
  readonly operation?: "create_plot";
  readonly action_id: string;
  readonly plot_id: string;
  readonly profile_id: string;
  readonly data: EngineDataRef;
  readonly bindings: ReadonlyArray<FieldBinding>;
}

export type DataFilterPredicate = {
  readonly field_id: string;
  readonly operator: "equal" | "not_equal" | "less_than" | "less_or_equal" | "greater_than" | "greater_or_equal" | "is_missing" | "is_not_missing" | "in_values";
  readonly value?: boolean | number | string | ReadonlyArray<boolean | number | string | null> | null;
}

export type DataJoinKey = {
  readonly left_field_id: string;
  readonly right_field_id: string;
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

export type DataSortKey = {
  readonly field_id: string;
  readonly direction?: "ascending" | "descending";
  readonly missing?: "first" | "last";
}

export type DataViewHandle = {
  readonly schema_version?: "data-view-handle.v2";
  readonly handle_id: string;
  readonly handle_version?: number;
  readonly task_id: string;
  readonly task_version: number;
  readonly item_id?: string | null;
  readonly parent_handle_ids?: ReadonlyArray<string>;
  readonly root_sources: ReadonlyArray<EngineDataRef>;
  readonly data: EngineDataRef;
  readonly operation_kind: "source" | "select_fields" | "rename_field" | "convert_type" | "filter_rows" | "sort_rows" | "deduplicate_rows" | "derive_column" | "convert_unit" | "reshape_wide_to_long" | "reshape_long_to_wide" | "concatenate" | "keyed_join" | "aggregate";
  readonly operation_hash: string;
  readonly data_hash: string;
  readonly artifact_hash: string;
  readonly row_count: number;
  readonly fields: ReadonlyArray<EngineField>;
  readonly lineage: ReadonlyArray<DataViewLineageStep>;
  readonly created_at: string;
  readonly expires_at: string;
}

export type DataViewLineageStep = {
  readonly step_id: string;
  readonly operation_kind: "source" | "select_fields" | "rename_field" | "convert_type" | "filter_rows" | "sort_rows" | "deduplicate_rows" | "derive_column" | "convert_unit" | "reshape_wide_to_long" | "reshape_long_to_wide" | "concatenate" | "keyed_join" | "aggregate";
  readonly input_handle_ids?: ReadonlyArray<string>;
  readonly input_data_hashes?: ReadonlyArray<string>;
  readonly parameters_hash: string;
  readonly output_data_hash: string;
}

export type DataViewOperationContract = SelectFieldsOperation | RenameFieldOperation | ConvertTypeOperation | FilterRowsOperation | SortRowsOperation | DeduplicateRowsOperation | DeriveColumnOperation | ConvertUnitOperation | ReshapeWideToLongOperation | ReshapeLongToWideOperation | ConcatenateOperation | KeyedJoinOperation | AggregateOperation

export type DataViewPreview = {
  readonly handle: DataViewHandle;
  readonly field_ids: ReadonlyArray<string>;
  readonly offset: number;
  readonly rows: ReadonlyArray<ReadonlyArray<boolean | number | string | null>>;
  readonly has_more: boolean;
}

export type DeduplicateRowsOperation = {
  readonly kind?: "deduplicate_rows";
  readonly input_handle_id: string;
  readonly key_field_ids: ReadonlyArray<string>;
  readonly keep?: "first" | "last";
}

export type DeriveColumn = {
  readonly operation?: "derive_column";
  readonly source_alias: string;
  readonly input_field_aliases: ReadonlyArray<string>;
  readonly operator: "add" | "subtract" | "multiply" | "divide" | "absolute" | "negate" | "log10" | "ln" | "sqrt";
  readonly scalar?: number | null;
  readonly output_field_alias: string;
  readonly output_name: string;
}

export type DeriveColumnOperation = {
  readonly kind?: "derive_column";
  readonly input_handle_id: string;
  readonly input_field_ids: ReadonlyArray<string>;
  readonly operator: "add" | "subtract" | "multiply" | "divide" | "absolute" | "negate" | "log10" | "ln" | "sqrt";
  readonly scalar?: number | null;
  readonly output_field_id: string;
  readonly output_name: string;
}

export type DomainExample = {
  readonly example_id: string;
  readonly kind: "minimal" | "representative" | "near_miss" | "invalid";
  readonly summary: string;
  readonly role_assignments: ReadonlyArray<readonly [string, string]>;
  readonly expected_outcome: "supported" | "needs_input" | "rejected";
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

export type DropEmptyFields = {
  readonly operation?: "drop_empty_fields";
  readonly source_alias: string;
  readonly field_aliases: ReadonlyArray<string>;
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
  readonly role_field_types?: Readonly<Record<string, never>>;
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

export type ExcludeRows = {
  readonly operation?: "exclude_rows";
  readonly source_alias: string;
  readonly row_indices: ReadonlyArray<number>;
}

export type ExecutionGrant = {
  readonly schema_version?: "execution-grant.v2";
  readonly grant_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly intent: IntentRef;
  readonly expected_project_revision: number;
  readonly permission_phase: "p2_confirmed" | "p3_expanded";
  readonly scopes: ReadonlyArray<ExecutionScope>;
  readonly issued_at: string;
  readonly expires_at?: string | null;
  readonly content_hash: string;
}

export type ExecutionScope = {
  readonly item_id: string;
  readonly operations: ReadonlyArray<string>;
  readonly target_object_ids?: ReadonlyArray<string>;
  readonly output_resources?: ReadonlyArray<ResourceRef>;
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

export type FilterRowsOperation = {
  readonly kind?: "filter_rows";
  readonly input_handle_id: string;
  readonly predicates: ReadonlyArray<DataFilterPredicate>;
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

export type IntentRef = {
  readonly intent_id: string;
  readonly intent_version: number;
  readonly content_hash: string;
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

export type JsonValue = unknown

export type KeyedJoinOperation = {
  readonly kind?: "keyed_join";
  readonly left_handle_id: string;
  readonly right_handle_id: string;
  readonly keys: ReadonlyArray<DataJoinKey>;
  readonly how?: "inner" | "left" | "right";
  readonly expected_relationship: "one_to_one" | "one_to_many" | "many_to_one";
  readonly right_field_prefix?: string;
}

export type LongToWideOutput = {
  readonly value: string;
  readonly field_id: string;
  readonly name: string;
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

export type RenameField = {
  readonly operation?: "rename_field";
  readonly source_alias: string;
  readonly field_alias: string;
  readonly output_field_alias: string;
  readonly output_name: string;
}

export type RenameFieldOperation = {
  readonly kind?: "rename_field";
  readonly input_handle_id: string;
  readonly field_id: string;
  readonly output_name: string;
}

export type RepairProposal = {
  readonly failed_report_ids: ReadonlyArray<string>;
  readonly affected_item_ids: ReadonlyArray<string>;
  readonly repair_operations: ReadonlyArray<string>;
  readonly preserves_confirmed_semantics?: true;
  readonly proposal_hash: string;
}

export type ReshapeLongToWide = {
  readonly operation?: "reshape_long_to_wide";
  readonly source_alias: string;
  readonly index_field_aliases: ReadonlyArray<string>;
  readonly name_field_alias: string;
  readonly value_field_alias: string;
  readonly output_fields: ReadonlyArray<WorkflowOutputField>;
}

export type ReshapeLongToWideOperation = {
  readonly kind?: "reshape_long_to_wide";
  readonly input_handle_id: string;
  readonly index_field_ids: ReadonlyArray<string>;
  readonly name_field_id: string;
  readonly value_field_id: string;
  readonly outputs: ReadonlyArray<LongToWideOutput>;
}

export type ReshapeWideToLong = {
  readonly operation?: "reshape_wide_to_long";
  readonly source_alias: string;
  readonly id_field_aliases?: ReadonlyArray<string>;
  readonly value_field_aliases: ReadonlyArray<string>;
  readonly output_name: string;
  readonly output_value: string;
}

export type ReshapeWideToLongOperation = {
  readonly kind?: "reshape_wide_to_long";
  readonly input_handle_id: string;
  readonly id_field_ids?: ReadonlyArray<string>;
  readonly value_field_ids: ReadonlyArray<string>;
  readonly output_name_field_id: string;
  readonly output_name: string;
  readonly output_value_field_id: string;
  readonly output_value_name: string;
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

export type ResourceRef = {
  readonly resource_id: string;
  readonly resource_kind: "authorized_file" | "authorized_directory" | "temporary_output";
}

export type RowExclusion = {
  readonly row_id: string;
  readonly field_id?: string | null;
  readonly reason: "missing" | "nan" | "positive_inf" | "negative_inf";
}

export type RowPage = {
  readonly source_alias: string;
  readonly field_aliases: ReadonlyArray<string>;
  readonly offset: number;
  readonly rows: ReadonlyArray<ReadonlyArray<boolean | number | string | null>>;
  readonly has_more: boolean;
}

export type SandboxPlotArtifact = {
  readonly artifact_id: string;
  readonly backend: "matplotlib" | "origin";
  readonly format: "png" | "svg" | "opju";
  readonly content_hash: string;
  readonly size: number;
}

export type SandboxPlotEditContract = SetTitle | SetAxis | SetSeriesStyle | SetLegend | SetColorMap | SetChartParameter | SetErrorStyle | SetDataLabels | AddAnnotation

export type SandboxPlotHandle = {
  readonly schema_version?: "sandbox-plot-handle.v2";
  readonly handle_id: string;
  readonly handle_version?: number;
  readonly task_id: string;
  readonly task_version: number;
  readonly item_id?: string | null;
  readonly parent_handle_id?: string | null;
  readonly data_view_handle_id: string;
  readonly root_sources: ReadonlyArray<EngineDataRef>;
  readonly staged_data_hash: string;
  readonly document: PlotDocument;
  readonly backends: ReadonlyArray<"matplotlib" | "origin">;
  readonly readbacks: ReadonlyArray<SandboxPlotReadback>;
  readonly artifacts: ReadonlyArray<SandboxPlotArtifact>;
  readonly lineage: ReadonlyArray<SandboxPlotLineageStep>;
  readonly created_at: string;
  readonly expires_at: string;
}

export type SandboxPlotLineageStep = {
  readonly step_id: string;
  readonly operation: "preview_plot" | "apply_plot_edits";
  readonly input_handle_id?: string | null;
  readonly action_ids: ReadonlyArray<string>;
  readonly action_hash: string;
  readonly output_document: PlotDocumentRef;
  readonly artifact_hashes: ReadonlyArray<string>;
}

export type SandboxPlotObject = {
  readonly semantic_id: string;
  readonly object_kind: string;
}

export type SandboxPlotReadback = {
  readonly backend: "matplotlib" | "origin";
  readonly document: PlotDocumentRef;
  readonly objects: ReadonlyArray<SandboxPlotObject>;
  readonly data_hash: string;
  readonly style_hash: string;
}

export type SelectFields = {
  readonly operation?: "select_fields";
  readonly source_alias: string;
  readonly field_aliases: ReadonlyArray<string>;
}

export type SelectFieldsOperation = {
  readonly kind?: "select_fields";
  readonly input_handle_id: string;
  readonly field_ids: ReadonlyArray<string>;
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

export type SelectedPlotBindingContext = {
  readonly role: string;
  readonly source_alias: string;
  readonly field_alias: string;
}

export type SelectedPlotContext = {
  readonly plot_alias: string;
  readonly plot_id: string;
  readonly plot_version: number;
  readonly profile_id: string;
  readonly source_aliases?: ReadonlyArray<string>;
  readonly bindings?: ReadonlyArray<SelectedPlotBindingContext>;
}

export type SelectedPlotRef = {
  readonly plot_id: string;
  readonly plot_version: number;
  readonly profile_id: string;
}

export type SemanticDecision = {
  readonly decision_id: string;
  readonly kind: "profile" | "field_binding" | "unit" | "ordering" | "filter" | "aggregation" | "calculation" | "visual" | "output";
  readonly summary: string;
  readonly evidence_refs?: ReadonlyArray<string>;
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

export type SideEffectReceipt = {
  readonly effect_kind: "none" | "project_revision" | "plot_version" | "staged_data_view" | "staged_plot" | "staged_file" | "published_file" | "origin_session";
  readonly object_id?: string | null;
  readonly object_version?: number | null;
  readonly resource?: ResourceRef | null;
  readonly artifact_hash?: string | null;
  readonly reversible?: boolean;
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

export type SortRowsOperation = {
  readonly kind?: "sort_rows";
  readonly input_handle_id: string;
  readonly keys: ReadonlyArray<DataSortKey>;
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

export type TaskBudgetEvent = {
  readonly event_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly sequence: number;
  readonly occurred_at: string;
  readonly event_type?: "task_budget";
  readonly budget: TaskBudgetSnapshot;
  readonly change_reason: "usage" | "policy_reduced" | "reconciled";
}

export type TaskBudgetLimits = {
  readonly max_model_calls?: number;
  readonly max_model_turns?: number;
  readonly max_input_tokens?: number;
  readonly max_output_tokens?: number;
  readonly max_tool_calls?: number;
  readonly max_disclosed_scalars?: number;
  readonly max_origin_sessions?: number;
  readonly max_repair_attempts?: number;
  readonly max_wall_time_ms?: number | null;
  readonly max_estimated_cost?: number;
}

export type TaskBudgetSnapshot = {
  readonly limits: TaskBudgetLimits;
  readonly usage?: TaskBudgetUsage;
}

export type TaskBudgetUsage = {
  readonly model_calls?: number;
  readonly model_turns?: number;
  readonly input_tokens?: number;
  readonly output_tokens?: number;
  readonly tool_calls?: number;
  readonly disclosed_scalars?: number;
  readonly origin_sessions?: number;
  readonly repair_attempts?: number;
  readonly wall_time_ms?: number;
  readonly estimated_cost?: number;
}

export type TaskCheckpoint = {
  readonly schema_version?: "task-checkpoint.v2";
  readonly checkpoint_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly state: "created" | "investigating" | "awaiting_input" | "intent_staged" | "awaiting_confirmation" | "executing" | "verifying" | "repairing" | "awaiting_reconfirmation" | "delivering" | "partial" | "blocked" | "unsupported" | "cancelling" | "cancelled" | "rejected" | "failed" | "completed_verified";
  readonly project_revision: number;
  readonly last_event_sequence: number;
  readonly intent?: IntentRef | null;
  readonly active_activation_id?: string | null;
  readonly items?: ReadonlyArray<TaskItemSnapshot>;
  readonly budget: TaskBudgetSnapshot;
  readonly completion?: TaskCompletion | null;
  readonly updated_at: string;
  readonly content_hash: string;
}

export type TaskCompletion = {
  readonly outcome?: "all_succeeded" | "completed_with_skips";
  readonly completed_at: string;
  readonly final_project_revision: number;
  readonly required_report_ids: ReadonlyArray<string>;
  readonly artifact_receipt_ids?: ReadonlyArray<string>;
  readonly skipped_item_ids?: ReadonlyArray<string>;
}

export type TaskDraft = {
  readonly schema_version?: "task-draft.v1";
  readonly draft_id: string;
  readonly workflow_run_id: string;
  readonly route: "agent" | "recipe_replay" | "direct";
  readonly summary: string;
  readonly items: ReadonlyArray<TaskDraftItem>;
  readonly confidence: number;
  readonly hard_constraints?: ReadonlyArray<string>;
}

export type TaskDraftItem = {
  readonly task_kind: "create" | "edit" | "update_data";
  readonly item_id: string;
  readonly plot_alias: string;
  readonly profile_id: string;
  readonly target_plot_alias?: string | null;
  readonly source_aliases?: ReadonlyArray<string>;
  readonly data_operations?: ReadonlyArray<SelectFields | FilterRows | SortRows | ExcludeRows | DropEmptyFields | ConvertType | ReshapeLongToWide | ReshapeWideToLong | ConcatenateSources | AlignSourcesOnX | RenameField | DeriveColumn | ConvertUnit | BucketizeNumeric>;
  readonly bindings?: ReadonlyArray<DraftFieldBinding>;
  readonly visual_actions?: ReadonlyArray<DraftSetTitle | DraftSetAxis | DraftSetSeriesStyle | DraftSetLegend | DraftSetColorMap | DraftSetErrorStyle | DraftSetDataLabels | DraftSetChartParameter | DraftAddAnnotation>;
}

export type TaskEnvelope = {
  readonly schema_version?: "task-envelope.v2";
  readonly task_id: string;
  readonly task_version: number;
  readonly project_id: string;
  readonly project_revision: number;
  readonly original_instruction: string;
  readonly parent_task_id?: string | null;
  readonly relationship?: "follow_up" | null;
  readonly locale?: "zh-CN" | "en-US";
  readonly selected_sources?: ReadonlyArray<SourceDatasetRef>;
  readonly selected_plots?: ReadonlyArray<SelectedPlotRef>;
  readonly selected_profile_ids?: ReadonlyArray<string>;
  readonly authorized_resources?: ReadonlyArray<ResourceRef>;
  readonly budget: TaskBudgetLimits;
  readonly created_at: string;
}

export type TaskError = {
  readonly code: string;
  readonly category: "transient_external" | "deterministic_technical" | "semantic_conflict" | "stale_or_concurrent" | "unsupported" | "safety_or_permission" | "budget" | "runtime";
  readonly message: string;
  readonly retryable: boolean;
  readonly requires_user: boolean;
  readonly side_effect_state: "known_none" | "known_applied" | "unknown";
  readonly diagnostic_id?: string | null;
}

export type TaskEventContract = TaskStateTransitionEvent | TaskItemTransitionEvent | AgentActivationEvent | UserTaskEvent | ToolReceiptEvent | VerificationReportEvent | TaskBudgetEvent

export type TaskIntent = {
  readonly schema_version?: "task-intent.v2";
  readonly intent_id: string;
  readonly intent_version: number;
  readonly task_id: string;
  readonly task_version: number;
  readonly created_by_activation_id: string;
  readonly summary: string;
  readonly items: ReadonlyArray<TaskDraftItem>;
  readonly semantic_decisions?: ReadonlyArray<SemanticDecision>;
  readonly context_hash: string;
  readonly content_hash: string;
}

export type TaskItemProgress = {
  readonly item_id: string;
  readonly state: "pending" | "running" | "succeeded" | "failed" | "blocked" | "cancelled";
  readonly attempt_count?: number;
  readonly error_code?: string | null;
  readonly error_message?: string | null;
  readonly error_retryable?: boolean | null;
  readonly output_plot_id?: string | null;
  readonly output_plot_version?: number | null;
}

export type TaskItemSnapshot = {
  readonly item_id: string;
  readonly state: "pending" | "staged" | "running" | "succeeded" | "repairable_failed" | "failed" | "blocked" | "cancelled";
  readonly attempt_count?: number;
  readonly last_error?: TaskError | null;
  readonly output_plot_id?: string | null;
  readonly output_plot_version?: number | null;
  readonly receipt_ids?: ReadonlyArray<string>;
  readonly verification_report_ids?: ReadonlyArray<string>;
}

export type TaskItemTransitionEvent = {
  readonly event_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly sequence: number;
  readonly occurred_at: string;
  readonly event_type?: "task_item_transition";
  readonly item_id: string;
  readonly previous_state: "pending" | "staged" | "running" | "succeeded" | "repairable_failed" | "failed" | "blocked" | "cancelled";
  readonly next_state: "pending" | "staged" | "running" | "succeeded" | "repairable_failed" | "failed" | "blocked" | "cancelled";
  readonly reason_code: string;
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

export type TaskStateTransitionEvent = {
  readonly event_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly sequence: number;
  readonly occurred_at: string;
  readonly event_type?: "task_state_transition";
  readonly previous_state: "created" | "investigating" | "awaiting_input" | "intent_staged" | "awaiting_confirmation" | "executing" | "verifying" | "repairing" | "awaiting_reconfirmation" | "delivering" | "partial" | "blocked" | "unsupported" | "cancelling" | "cancelled" | "rejected" | "failed" | "completed_verified";
  readonly next_state: "created" | "investigating" | "awaiting_input" | "intent_staged" | "awaiting_confirmation" | "executing" | "verifying" | "repairing" | "awaiting_reconfirmation" | "delivering" | "partial" | "blocked" | "unsupported" | "cancelling" | "cancelled" | "rejected" | "failed" | "completed_verified";
  readonly reason_code: string;
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

export type ToolContract = {
  readonly schema_version?: "tool-contract.v2";
  readonly contract_id: string;
  readonly contract_version: number;
  readonly tool_name: string;
  readonly description: string;
  readonly permission_phase: "p0_read" | "p1_staged" | "p2_confirmed" | "p3_expanded";
  readonly side_effect: "none" | "staged" | "committed" | "expanded_risk";
  readonly allowed_task_states: ReadonlyArray<"created" | "investigating" | "awaiting_input" | "intent_staged" | "awaiting_confirmation" | "executing" | "verifying" | "repairing" | "awaiting_reconfirmation" | "delivering" | "partial" | "blocked" | "unsupported" | "cancelling" | "cancelled" | "rejected" | "failed" | "completed_verified">;
  readonly input_schema_hash: string;
  readonly output_schema_hash: string;
  readonly cost_class: "cheap" | "moderate" | "expensive";
  readonly timeout_ms: number;
  readonly max_disclosed_scalars?: number;
  readonly uses_origin?: boolean;
}

export type ToolInvocation = {
  readonly schema_version?: "tool-invocation.v2";
  readonly tool_call_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly activation_id: string;
  readonly item_id?: string | null;
  readonly execution_grant_id?: string | null;
  readonly idempotency_key?: string | null;
  readonly tool_name: string;
  readonly permission_phase: "p0_read" | "p1_staged" | "p2_confirmed" | "p3_expanded";
  readonly arguments_hash: string;
  readonly activation_tool_calls_before: number;
  readonly activation_disclosed_scalars_before: number;
  readonly expected_project_revision?: number;
  readonly deadline: string;
}

export type ToolProvenance = {
  readonly source_id: string;
  readonly source_version?: number | null;
  readonly content_hash?: string | null;
  readonly coordinate?: string | null;
}

export type ToolReceipt = {
  readonly schema_version?: "tool-receipt.v2";
  readonly receipt_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly activation_id?: string | null;
  readonly item_id?: string | null;
  readonly tool_call_id: string;
  readonly tool_name: string;
  readonly permission_phase: "p0_read" | "p1_staged" | "p2_confirmed" | "p3_expanded";
  readonly outcome: "succeeded" | "failed" | "cancelled" | "unknown";
  readonly idempotency_key?: string | null;
  readonly input_hash: string;
  readonly output_hash?: string | null;
  readonly project_revision_before: number;
  readonly project_revision_after: number;
  readonly side_effects?: ReadonlyArray<SideEffectReceipt>;
  readonly budget_delta?: TaskBudgetUsage;
  readonly error?: TaskError | null;
  readonly started_at: string;
  readonly finished_at: string;
}

export type ToolReceiptEvent = {
  readonly event_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly sequence: number;
  readonly occurred_at: string;
  readonly event_type?: "tool_receipt";
  readonly receipt: ToolReceipt;
}

export type ToolWarning = {
  readonly code: string;
  readonly message: string;
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

export type UntrustedSourceContext = {
  readonly content_is_untrusted?: true;
  readonly source: WorkflowSource;
  readonly fields?: ReadonlyArray<WorkflowField>;
  readonly preview?: RowPage | null;
}

export type UserTaskEvent = {
  readonly event_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly sequence: number;
  readonly occurred_at: string;
  readonly event_type?: "user_task_event";
  readonly action: "answered" | "confirmed" | "rejected" | "corrected" | "cancel_requested" | "partial_accepted" | "retry_requested" | "resumed";
  readonly user_event_id: string;
  readonly payload_hash: string;
  readonly message?: string | null;
}

export type VerificationClaim = {
  readonly claim_id: string;
  readonly requirement?: "required" | "advisory";
  readonly status: "passed" | "failed" | "blocked" | "unknown";
  readonly expected: string;
  readonly observed: string;
  readonly evidence?: ReadonlyArray<VerificationEvidenceRef>;
  readonly repair_scope?: ReadonlyArray<string>;
  readonly error?: TaskError | null;
}

export type VerificationEvidenceRef = {
  readonly evidence_id: string;
  readonly evidence_kind: "task_state" | "data_snapshot" | "plot_document" | "backend_readback" | "artifact" | "fresh_reopen" | "visual_review" | "tool_receipt";
  readonly content_hash: string;
}

export type VerificationReport = {
  readonly schema_version?: "verification-report.v2";
  readonly report_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly intent: IntentRef;
  readonly item_id?: string | null;
  readonly status: "passed" | "failed" | "blocked" | "unknown";
  readonly claims: ReadonlyArray<VerificationClaim>;
  readonly content_hash: string;
  readonly verified_at: string;
}

export type VerificationReportEvent = {
  readonly event_id: string;
  readonly task_id: string;
  readonly task_version: number;
  readonly sequence: number;
  readonly occurred_at: string;
  readonly event_type?: "verification_report";
  readonly report: VerificationReport;
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
  readonly unit_evidence?: "none" | "declared" | "suffix_candidate";
}

export type WorkflowNeedsInput = {
  readonly outcome?: "needs_input";
  readonly workflow_run_id: string;
  readonly questions: ReadonlyArray<InputQuestion>;
}

export type WorkflowOutputField = {
  readonly field_alias: string;
  readonly name: string;
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
  readonly state: "routing" | "agent" | "recipe_replay" | "direct" | "needs_input" | "draft_ready" | "awaiting_confirmation" | "executing" | "completed" | "partially_succeeded" | "failed" | "cancelled";
  readonly route?: "agent" | "recipe_replay" | "direct" | null;
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
