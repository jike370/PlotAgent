"""Versioned chart and calculation knowledge derived from executable contracts."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from pydantic import BaseModel, TypeAdapter

from plotagent.contracts.base import CalculationKind, ChartTypeId
from plotagent.contracts.calculations import (
    ConfusionCountSpec,
    ECDFSpec,
    HistogramBinningSpec,
    MatrixProjectionSpec,
    PercentStackSpec,
    SummaryErrorSpec,
    TukeyBoxSpec,
    ViolinKDESpec,
)
from plotagent.contracts.canonical import canonical_hash
from plotagent.contracts.domain_knowledge import (
    CalculationContract,
    CalculationInputRole,
    CalculationParameter,
    ChartCatalogEntry,
    ChartEvidenceRef,
    ChartKnowledgeCard,
    ChartProfileComparison,
    DomainExample,
)
from plotagent.engine.backends.origin.recipe import ORIGIN_RECIPES, OriginRecipe
from plotagent.engine.contracts import EngineProfile
from plotagent.engine.profiles import ENGINE_PROFILES
from plotagent.plot_calculations.service import ALGORITHM_VERSION

type _CalculationSpecType = type[BaseModel]


class DomainKnowledgeError(LookupError):
    """Stable fail-closed lookup error for absent or stale product knowledge."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_CALCULATION_PROFILES: dict[CalculationKind, tuple[ChartTypeId, ...]] = {
    "histogram_binning": ("K15",),
    "tukey_box": ("K13",),
    "violin_kde": ("K14",),
    "ecdf": (),
    "summary_error": ("K06", "K07"),
    "percent_stack": ("K11",),
    "matrix_projection": ("K20", "K21", "K22"),
    "confusion_count": ("S61",),
}

_PROFILE_CALCULATIONS: dict[ChartTypeId, tuple[str, ...]] = {
    cast(ChartTypeId, profile_id): tuple(
        f"calculation:{kind}.v1"
        for kind, profile_ids in _CALCULATION_PROFILES.items()
        if profile_id in profile_ids
    )
    for profile_id in (profile.profile_id for profile in ENGINE_PROFILES)
}

_ORDERING: dict[ChartTypeId, tuple[str, ...]] = {
    "K01": ("按来源行与 X 的既定顺序连接，不自动排序或平滑。",),
    "K02": ("按来源行与 X 的既定顺序连接，不自动排序。",),
    "K09": ("类别和分组顺序保留来源或用户显式指定的顺序。",),
    "K10": ("类别顺序和堆叠系列顺序均有语义，不静默重排。",),
    "K11": ("类别顺序和百分比堆叠顺序均有语义，不静默重排。",),
    "K19": ("时间点按来源顺序连接；排序需要成为显式数据动作。",),
    "S34": ("阻抗点及可选频率元数据的来源顺序必须保留。",),
    "X03": ("每个来源行跨多个 Y 字段形成连接关系，不转置成逐行独立系列。",),
    "X09": ("边界字段按 start→middle→end 的原始列顺序组成相邻区间，不排序数值。",),
    "X24": ("Pareto 排序属于该计算/图类的显式语义，不能由通用清洗提前改写来源。",),
    "X39": ("每个来源行跨 Y 列连接，列顺序定义线序列位置。",),
    "X40": ("Before 与 After 保持相邻配对；subject 行身份和来源顺序不可丢失。",),
}

_FIXED: dict[ChartTypeId, tuple[str, ...]] = {
    "K04": ("X/Y 决定位置，size 决定气泡面积，color 决定连续颜色映射。",),
    "K06": (
        "X 与 Y 误差是不同方向的不确定性，不能互换。",
        "x_err_minus/x_err_plus/y_err_minus/y_err_plus 接受非负误差幅度；"
        "若来源提供绝对下界/上界，必须先显式派生中心到边界的差值，不能把边界值直接绑定为误差幅度。",
    ),
    "K07": ("lower/upper 表示围绕中心的上下界，填充区域只位于两界之间。",),
    "K11": ("每个类别按原始非负分量归一为 100%，来源值保持未归一化。",),
    "K13": ("箱体为 25%–75%，须采用 Tukey 1.5×IQR，离群点单独保留。",),
    "K14": ("密度使用冻结的高斯 KDE 合同；原始观测不被预聚合。",),
    "K15": ("直方分箱由冻结的 Freedman–Diaconis/Sturges 合同决定，默认高度为计数。",),
    "K19": ("X 是数值日期时间轴而不是等距文本类别。",),
    "K20": (
        "row 字段决定矩阵行和 Y 轴，column 字段决定矩阵列和 X 轴，"
        "value 决定单元格颜色；三者不能互换。",
        "公开色板名 RdBu 对应 palette=red_white_blue；反转必须单独写 reverse=true，"
        "不能再交换成 blue_white_red。set_colormap 的目标是 series_1。",
    ),
    "S34": ("横轴为阻抗实部，纵轴为负虚部；frequency 仅作元数据。",),
    "S61": ("行是 Actual、列是 Predicted；可从逐条记录计数或使用非负整数 Count。",),
    "X13": ("左右两个数值系列共享中央类别轴，不能退化为普通并列条形图。",),
    "X23": ("左右 Y 独立缩放、共享同一 X；两个系列均为线点对象。",),
    "X35": ("左右 Y 独立缩放且均为从零基线起始的普通柱，不得变成浮动柱。",),
    "X36": ("左侧为柱、右侧为线点，两个 Y 轴独立缩放并共享 X。",),
    "X39": ("源表保持宽表；每行跨多个 Y 列形成一条线序列关系。",),
    "X40": ("源表保持宽表；Before/After 按行成对连接并保留 subject 身份。",),
}

_FORBIDDEN: dict[ChartTypeId, tuple[str, ...]] = {
    "K06": ("禁止把 X 误差复制为 Y 误差，或反向复制。",),
    "K07": ("禁止把 lower/upper 当成普通独立系列，或猜测误差类型。",),
    "K11": ("禁止在来源表中预先百分比化或累计化以伪装原生百分比堆叠。",),
    "K13": ("禁止以 5%/95% 默认须或后端默认值冒充 Tukey 1.5×IQR。",),
    "K14": ("禁止把预计算密度曲线或后端默认带宽冒充冻结 KDE 合同。",),
    "K15": ("禁止预计算普通柱来伪装原生直方图。",),
    "K19": ("禁止静默排序、重采样、插值或剥离时区偏移。",),
    "S34": ("禁止二次取负虚部或按频率静默重排。",),
    "X09": ("禁止排序边界、取 min/max、复制 end，或把每个区间重建成独立普通柱。",),
    "X39": ("禁止转置来源表或把每个来源行物化为独立普通 XY 系列。",),
    "X40": ("禁止转置来源表、丢弃 subject 身份或跨行重新配对。",),
}


def _profile_by_id() -> dict[ChartTypeId, EngineProfile]:
    return {cast(ChartTypeId, profile.profile_id): profile for profile in ENGINE_PROFILES}


def _role_example(profile: EngineProfile) -> tuple[tuple[str, str], ...]:
    return tuple(
        (role, f"选择一个能够承担 {role} 语义的真实字段")
        for role in profile.required_roles
    )


def _build_card(profile: EngineProfile, recipe: OriginRecipe) -> ChartKnowledgeCard:
    profile_id = profile.profile_id
    if profile_id != recipe.profile_id:
        raise RuntimeError("EngineProfile and reviewed recipe identities differ")
    claims = (
        f"profile:{profile_id}.engine_contract",
        f"profile:{profile_id}.source_binding",
        f"profile:{profile_id}.editable_artifact",
    )
    requirements = tuple(f"输入要求：{item}" for item in recipe.designation_contract)
    fixed = _FIXED.get(
        profile_id,
        (
            "图形语义由公开角色合同和来源绑定决定；视觉编辑不得改变字段含义。",
        ),
    )
    ordering = _ORDERING.get(
        profile_id,
        ("保持来源行、类别和系列的既定顺序；任何重排都需要显式语义决定。",),
    )
    forbidden = (
        "禁止仅凭列名、数值形状或关键词静默选择字段、单位、聚合或图类。",
        "禁止为满足 renderer 形状而复制、覆盖或丢弃原始观测。",
        *_FORBIDDEN.get(profile_id, ()),
    )
    examples = (
        DomainExample(
            example_id=f"example:{profile_id}.minimal",
            kind="minimal",
            summary=f"满足 {recipe.chinese_name} 必填角色的最小来源表。",
            role_assignments=_role_example(profile),
            expected_outcome="supported",
        ),
        DomainExample(
            example_id=f"example:{profile_id}.near_miss",
            kind="near_miss",
            summary="来源缺少至少一个必填语义角色，或字段含义仍有多个合理解释。",
            role_assignments=(),
            expected_outcome="needs_input",
        ),
    )
    evidence = ChartEvidenceRef(
        evidence_id=f"evidence:{profile_id}.origin2024",
        title=f"Origin 官方 {recipe.official_name} 说明与 PlotAgent 审核证据",
        official_url=recipe.official_help_url,
        reviewed_product_version="OriginPro-2024-10.1.0.178",
        evidence_digest=canonical_hash(recipe),
        claim_ids=claims,
    )
    return ChartKnowledgeCard(
        knowledge_id=f"knowledge:{profile_id}.v1",
        knowledge_version=1,
        profile_id=profile_id,
        engine_profile=profile,
        engine_profile_hash=canonical_hash(profile),
        display_name_zh=recipe.chinese_name,
        official_name=recipe.official_name,
        user_facing_description=(
            f"{recipe.chinese_name}用于表达由 {', '.join(profile.required_roles)} "
            "等公开角色定义的数据关系；字段含义必须由任务事实确认。"
        ),
        intended_questions=(
            f"当研究问题需要用 {recipe.official_name} 的结构表达数据关系时。",
        ),
        unsuitable_questions=(
            "当数据无法满足必填角色或行间关系，且用户未授权整理或补充语义时。",
        ),
        source_shapes=(recipe.source_layout,),
        data_requirements=requirements,
        row_relations=("每个绘图对象必须可追溯到授权来源字段和来源行。",),
        ordering_semantics=ordering,
        fixed_scientific_semantics=fixed,
        allowed_preparations=(
            "可以预览并暂存不改变科学含义的结构整理，但执行前必须保留 lineage。",
            "字段选择、单位换算、排序、筛选、聚合和配对均由 Agent 显式提出。",
        ),
        forbidden_preparations=forbidden,
        unsupported_actions=(
            "不支持 EngineProfile 未声明的对象或视觉动作。",
            "不支持把后端私有属性、脚本或对象编号作为 Agent 操作。",
        ),
        calculation_contract_ids=_PROFILE_CALCULATIONS[profile_id],
        examples=examples,
        validation_claims=claims,
        evidence_refs=(evidence,),
    )


def _schema_hash(spec_type: _CalculationSpecType) -> str:
    return canonical_hash(TypeAdapter(spec_type).json_schema(mode="validation"))


def _numeric_role(role: str, required: bool = True) -> CalculationInputRole:
    return CalculationInputRole(role=role, accepted_types=("numeric",), required=required)


def _categorical_role(role: str, required: bool = True) -> CalculationInputRole:
    return CalculationInputRole(
        role=role,
        accepted_types=("categorical", "text"),
        required=required,
    )


def _calculation_contracts() -> tuple[CalculationContract, ...]:
    common_missing = (
        "missing_policy=fail 拒绝缺失或非有限输入；"
        "missing_policy=exclude_with_report 仅排除受影响行并记录 lineage。"
    )
    return (
        CalculationContract(
            contract_id="calculation:histogram_binning.v1",
            contract_version=1,
            calculation_kind="histogram_binning",
            algorithm_id="freedman_diaconis_sturges",
            algorithm_version=ALGORITHM_VERSION,
            spec_schema_hash=_schema_hash(HistogramBinningSpec),
            input_roles=(_numeric_role("value"),),
            definition=(
                "优先使用 Freedman–Diaconis 宽度；IQR 为零时使用 Sturges；"
                "常量数据使用确定性单箱边界。",
                "输出固定的左界、右界、中心、计数及 count/density 高度。",
            ),
            parameters=(
                CalculationParameter(
                    name="normalization",
                    value_type="enum",
                    default="count",
                    constraint="仅允许 count 或 density。",
                ),
            ),
            missing_value_behavior=common_missing,
            boundary_behavior=("所有有效观测必须有限；输出箱覆盖全部有效值。",),
            output_fields=(
                "field:plotcalc.bin_index",
                "field:plotcalc.bin_left",
                "field:plotcalc.bin_right",
                "field:plotcalc.bin_center",
                "field:plotcalc.count",
                "field:plotcalc.value",
            ),
            linked_profile_ids=_CALCULATION_PROFILES["histogram_binning"],
            oracle_ids=("oracle:histogram.geometry.v1",),
        ),
        CalculationContract(
            contract_id="calculation:tukey_box.v1",
            contract_version=1,
            calculation_kind="tukey_box",
            algorithm_id="linear_quantile_tukey_1_5_iqr",
            algorithm_version=ALGORITHM_VERSION,
            spec_schema_hash=_schema_hash(TukeyBoxSpec),
            input_roles=(_numeric_role("value"), _categorical_role("group", False)),
            definition=(
                "使用 linear quantile 计算 Q1、median、Q3；围栏为 Q1/Q3 ± 1.5×IQR。",
                "须止于围栏内最外侧观测，围栏外观测保留为带来源行 ID 的离群点。",
            ),
            missing_value_behavior=common_missing,
            boundary_behavior=("每组必须至少保留一个有效数值。",),
            output_fields=(
                "field:plotcalc.record_kind",
                "field:plotcalc.group_index",
                "field:plotcalc.group",
                "field:plotcalc.n",
                "field:plotcalc.q1",
                "field:plotcalc.median",
                "field:plotcalc.q3",
                "field:plotcalc.iqr",
                "field:plotcalc.lower_fence",
                "field:plotcalc.upper_fence",
                "field:plotcalc.whisker_low",
                "field:plotcalc.whisker_high",
                "field:plotcalc.outlier_value",
                "field:plotcalc.outlier_row_id",
            ),
            linked_profile_ids=_CALCULATION_PROFILES["tukey_box"],
            oracle_ids=("oracle:tukey.linear_quantile.v1",),
        ),
        CalculationContract(
            contract_id="calculation:violin_kde.v1",
            contract_version=1,
            calculation_kind="violin_kde",
            algorithm_id="gaussian_scott_observed_range",
            algorithm_version=ALGORITHM_VERSION,
            spec_schema_hash=_schema_hash(ViolinKDESpec),
            input_roles=(_numeric_role("value"), _categorical_role("group", False)),
            definition=(
                "每组使用高斯 KDE 与冻结 Scott 带宽，在观测范围内计算 256 点密度。",
            ),
            parameters=(
                CalculationParameter(
                    name="grid_points",
                    value_type="integer",
                    default=256,
                    constraint="v1 固定为 256。",
                ),
            ),
            missing_value_behavior=common_missing,
            boundary_behavior=("每组至少两个有效观测且样本方差必须为正。",),
            output_fields=(
                "field:plotcalc.group_index",
                "field:plotcalc.group",
                "field:plotcalc.grid_index",
                "field:plotcalc.x",
                "field:plotcalc.density",
                "field:plotcalc.bandwidth",
                "field:plotcalc.n",
            ),
            linked_profile_ids=_CALCULATION_PROFILES["violin_kde"],
            oracle_ids=("oracle:kde.scott.v1",),
        ),
        CalculationContract(
            contract_id="calculation:ecdf.v1",
            contract_version=1,
            calculation_kind="ecdf",
            algorithm_id="right_continuous_empirical_cdf",
            algorithm_version=ALGORITHM_VERSION,
            spec_schema_hash=_schema_hash(ECDFSpec),
            input_roles=(_numeric_role("value"),),
            definition=("按唯一数值排序并计算右连续 ECDF 或 CCDF，不插值。",),
            parameters=(
                CalculationParameter(
                    name="mode",
                    value_type="enum",
                    default="ecdf",
                    constraint="仅允许 ecdf 或 ccdf。",
                ),
            ),
            missing_value_behavior=common_missing,
            boundary_behavior=("至少保留一个有效观测；重复值合并到同一阶跃。",),
            output_fields=(
                "field:plotcalc.point_index",
                "field:plotcalc.x",
                "field:plotcalc.cumulative_count",
                "field:plotcalc.probability",
            ),
            linked_profile_ids=(),
            oracle_ids=("oracle:ecdf.right_continuous.v1",),
        ),
        CalculationContract(
            contract_id="calculation:summary_error.v1",
            contract_version=1,
            calculation_kind="summary_error",
            algorithm_id="fixed_summary_error",
            algorithm_version=ALGORITHM_VERSION,
            spec_schema_hash=_schema_hash(SummaryErrorSpec),
            input_roles=(
                _numeric_role("value", False),
                _numeric_role("center", False),
                _numeric_role("lower", False),
                _numeric_role("upper", False),
                _numeric_role("symmetric_error", False),
                _categorical_role("group", False),
            ),
            definition=(
                "支持 mean±SD、mean±SEM、mean 95% t CI、median/IQR、median/range，"
                "以及直接上下界或对称误差。",
                "计算型方法每组使用 sample SD(ddof=1)；直接输入保持来源行 lineage。",
            ),
            parameters=(
                CalculationParameter(
                    name="method",
                    value_type="enum",
                    constraint="必须从 SummaryMethod 封闭枚举中选择。",
                ),
            ),
            missing_value_behavior=common_missing,
            boundary_behavior=(
                "计算型方法每组至少两个有效观测。",
                "直接上下界必须满足 lower≤center≤upper；对称误差必须非负。",
            ),
            output_fields=(
                "field:plotcalc.group_index",
                "field:plotcalc.source_row_id",
                "field:plotcalc.n",
                "field:plotcalc.center",
                "field:plotcalc.lower",
                "field:plotcalc.upper",
                "field:plotcalc.error_minus",
                "field:plotcalc.error_plus",
            ),
            linked_profile_ids=_CALCULATION_PROFILES["summary_error"],
            oracle_ids=("oracle:summary_error.v1",),
        ),
        CalculationContract(
            contract_id="calculation:percent_stack.v1",
            contract_version=1,
            calculation_kind="percent_stack",
            algorithm_id="category_nonnegative_percent",
            algorithm_version=ALGORITHM_VERSION,
            spec_schema_hash=_schema_hash(PercentStackSpec),
            input_roles=(
                _categorical_role("category"),
                _categorical_role("component"),
                _numeric_role("value"),
            ),
            definition=("每个 category 内按非负 component 原始值计算比例与百分比。",),
            missing_value_behavior=common_missing,
            boundary_behavior=(
                "category/component 单元必须唯一，值必须非负，每个类别总和必须大于零。",
            ),
            output_fields=(
                "field:plotcalc.category_index",
                "field:plotcalc.component_index",
                "field:plotcalc.source_row_id",
                "field:plotcalc.original_value",
                "field:plotcalc.category_total",
                "field:plotcalc.proportion",
                "field:plotcalc.percent",
            ),
            linked_profile_ids=_CALCULATION_PROFILES["percent_stack"],
            oracle_ids=("oracle:percent_stack.v1",),
        ),
        CalculationContract(
            contract_id="calculation:matrix_projection.v1",
            contract_version=1,
            calculation_kind="matrix_projection",
            algorithm_id="regular_or_unique_xy_projection",
            algorithm_version=ALGORITHM_VERSION,
            spec_schema_hash=_schema_hash(MatrixProjectionSpec),
            input_roles=(
                _numeric_role("matrix_values", False),
                _numeric_role("x", False),
                _numeric_role("y", False),
                _numeric_role("z", False),
            ),
            definition=(
                "接受规则矩阵，或将唯一的 X/Y/Z 坐标投影到按 Y、X 排序的矩阵索引。",
            ),
            parameters=(
                CalculationParameter(
                    name="input_mode",
                    value_type="enum",
                    constraint="仅允许 regular_matrix 或 unique_xy。",
                ),
            ),
            missing_value_behavior=common_missing,
            boundary_behavior=("unique_xy 坐标必须唯一；输出明确报告网格是否完整。",),
            output_fields=(
                "field:plotcalc.matrix_row_index",
                "field:plotcalc.matrix_column_index",
                "field:plotcalc.value",
            ),
            linked_profile_ids=_CALCULATION_PROFILES["matrix_projection"],
            oracle_ids=("oracle:matrix_projection.v1",),
        ),
        CalculationContract(
            contract_id="calculation:confusion_count.v1",
            contract_version=1,
            calculation_kind="confusion_count",
            algorithm_id="fixed_confusion_count",
            algorithm_version=ALGORITHM_VERSION,
            spec_schema_hash=_schema_hash(ConfusionCountSpec),
            input_roles=(
                _categorical_role("actual"),
                _categorical_role("predicted"),
                _numeric_role("count", False),
            ),
            definition=(
                "按 Actual×Predicted 聚合逐条记录，或使用显式非负整数 Count；"
                "类别顺序保留首现或显式顺序。",
            ),
            parameters=(
                CalculationParameter(
                    name="normalization",
                    value_type="enum",
                    default="count",
                    constraint="仅允许 count、true_class 或 predicted_class。",
                ),
            ),
            missing_value_behavior=common_missing,
            boundary_behavior=(
                "预聚合 Count 必须是非负整数；显式类别顺序必须覆盖全部观测类别。",
            ),
            output_fields=(
                "field:plotcalc.actual_index",
                "field:plotcalc.actual_category",
                "field:plotcalc.predicted_index",
                "field:plotcalc.predicted_category",
                "field:plotcalc.count",
                "field:plotcalc.actual_total",
                "field:plotcalc.predicted_total",
                "field:plotcalc.value",
            ),
            linked_profile_ids=_CALCULATION_PROFILES["confusion_count"],
            oracle_ids=("oracle:confusion_count.v1",),
        ),
    )


class DomainKnowledgeRegistry:
    def __init__(self) -> None:
        profiles = _profile_by_id()
        if set(profiles) != set(ORIGIN_RECIPES):
            raise RuntimeError("EngineProfile and reviewed recipe inventories differ")
        cards = {
            profile_id: _build_card(profile, ORIGIN_RECIPES[profile_id])
            for profile_id, profile in profiles.items()
        }
        calculations = {item.contract_id: item for item in _calculation_contracts()}
        missing_calculations = {
            contract_id
            for card in cards.values()
            for contract_id in card.calculation_contract_ids
            if contract_id not in calculations
        }
        if missing_calculations:
            raise RuntimeError("chart knowledge references unavailable calculation contracts")
        self._cards: Mapping[ChartTypeId, ChartKnowledgeCard] = MappingProxyType(cards)
        self._calculations: Mapping[str, CalculationContract] = MappingProxyType(calculations)

    @property
    def cards(self) -> Mapping[ChartTypeId, ChartKnowledgeCard]:
        return self._cards

    @property
    def calculations(self) -> Mapping[str, CalculationContract]:
        return self._calculations

    def list_chart_catalog(self) -> tuple[ChartCatalogEntry, ...]:
        return tuple(self._catalog_entry(card) for card in self._cards.values())

    def get_chart_knowledge(
        self, profile_id: str, *, knowledge_version: int | None = None
    ) -> ChartKnowledgeCard:
        try:
            card = self._cards[profile_id]  # type: ignore[index]
        except KeyError as error:
            raise DomainKnowledgeError(
                "DOMAIN_KNOWLEDGE_UNAVAILABLE",
                f"no reviewed chart knowledge is available for {profile_id}",
            ) from error
        if knowledge_version is not None and knowledge_version != card.knowledge_version:
            raise DomainKnowledgeError(
                "DOMAIN_KNOWLEDGE_VERSION_MISMATCH",
                f"chart knowledge {profile_id} is not available at version {knowledge_version}",
            )
        return card

    def compare_chart_profiles(self, profile_ids: tuple[str, ...]) -> ChartProfileComparison:
        if len(profile_ids) < 2 or len(profile_ids) > 8 or len(profile_ids) != len(
            set(profile_ids)
        ):
            raise DomainKnowledgeError(
                "DOMAIN_COMPARISON_INVALID",
                "profile comparison requires two to eight unique profile ids",
            )
        cards = tuple(self.get_chart_knowledge(profile_id) for profile_id in profile_ids)
        typed_ids = tuple(card.profile_id for card in cards)
        return ChartProfileComparison(
            profile_ids=typed_ids,
            entries=tuple(self._catalog_entry(card) for card in cards),
            source_shapes={card.profile_id: card.source_shapes for card in cards},
            fixed_semantics={
                card.profile_id: card.fixed_scientific_semantics for card in cards
            },
            forbidden_preparations={
                card.profile_id: card.forbidden_preparations for card in cards
            },
        )

    def get_calculation_contract(
        self, contract_id: str, *, contract_version: int | None = None
    ) -> CalculationContract:
        try:
            contract = self._calculations[contract_id]
        except KeyError as error:
            raise DomainKnowledgeError(
                "CALCULATION_CONTRACT_UNAVAILABLE",
                f"no reviewed calculation contract is available for {contract_id}",
            ) from error
        if contract_version is not None and contract_version != contract.contract_version:
            raise DomainKnowledgeError(
                "CALCULATION_CONTRACT_VERSION_MISMATCH",
                f"calculation contract {contract_id} is not available "
                f"at version {contract_version}",
            )
        return contract

    def get_domain_example(self, example_id: str) -> DomainExample:
        for card in self._cards.values():
            for example in card.examples:
                if example.example_id == example_id:
                    return example
        raise DomainKnowledgeError(
            "DOMAIN_EXAMPLE_UNAVAILABLE",
            f"no reviewed domain example is available for {example_id}",
        )

    @staticmethod
    def _catalog_entry(card: ChartKnowledgeCard) -> ChartCatalogEntry:
        return ChartCatalogEntry(
            profile_id=card.profile_id,
            knowledge_id=card.knowledge_id,
            knowledge_version=card.knowledge_version,
            knowledge_hash=canonical_hash(card),
            display_name_zh=card.display_name_zh,
            official_name=card.official_name,
            summary=card.user_facing_description,
            required_roles=card.engine_profile.required_roles,
            optional_roles=card.engine_profile.optional_roles,
            repeatable_role_prefixes=card.engine_profile.repeatable_role_prefixes,
        )


DOMAIN_KNOWLEDGE = DomainKnowledgeRegistry()
