"""Read-only Agent tools over PlotAgent's reviewed domain registry."""

from __future__ import annotations

from typing import Annotated, cast

from pydantic import BaseModel, Field

from plotagent.contracts.agent_tasks import TaskState
from plotagent.contracts.base import ChartTypeId, StrictModel
from plotagent.contracts.domain_knowledge import (
    CalculationContract,
    CalculationContractId,
    ChartCatalogEntry,
    ChartKnowledgeCard,
    ChartProfileComparison,
    DomainExample,
    DomainExampleId,
)
from plotagent.domain.knowledge import DOMAIN_KNOWLEDGE, DomainKnowledgeError
from plotagent.tooling.gateway import (
    ToolExecutionOutput,
    ToolExecutionProblem,
    ToolGateway,
    ToolHandler,
)

_READ_STATES: tuple[TaskState, ...] = ("created", "investigating", "repairing")


class ListChartCatalogInput(StrictModel):
    pass


class ListChartCatalogOutput(StrictModel):
    entries: Annotated[tuple[ChartCatalogEntry, ...], Field(min_length=1, max_length=64)]


class GetChartKnowledgeInput(StrictModel):
    profile_id: ChartTypeId
    knowledge_version: int | None = Field(default=None, ge=1)


class CompareChartProfilesInput(StrictModel):
    profile_ids: Annotated[tuple[ChartTypeId, ...], Field(min_length=2, max_length=8)]


class GetCalculationContractInput(StrictModel):
    contract_id: CalculationContractId
    contract_version: int | None = Field(default=None, ge=1)


class GetDomainExampleInput(StrictModel):
    example_id: DomainExampleId


def _knowledge_problem(error: DomainKnowledgeError) -> ToolExecutionProblem:
    return ToolExecutionProblem(
        code=error.code,
        category="AGENT_REPAIRABLE",
        message=str(error),
        retryable=True,
        requires_user=False,
        repair_hint=(
            "Use list_chart_catalog or the selected chart card, then retry with an available "
            "identifier and version."
        ),
    )


def _list_catalog(_input: BaseModel) -> ToolExecutionOutput:
    entries = DOMAIN_KNOWLEDGE.list_chart_catalog()
    return ToolExecutionOutput(
        payload=ListChartCatalogOutput(entries=entries),
        summary=f"Returned {len(entries)} reviewed chart profiles.",
    )


def _get_chart(input_model: BaseModel) -> ToolExecutionOutput:
    request = cast(GetChartKnowledgeInput, input_model)
    try:
        card = DOMAIN_KNOWLEDGE.get_chart_knowledge(
            request.profile_id,
            knowledge_version=request.knowledge_version,
        )
    except DomainKnowledgeError as error:
        raise _knowledge_problem(error) from error
    return ToolExecutionOutput(
        payload=card,
        summary=f"Returned reviewed chart knowledge for {card.profile_id}.",
        output_handle=card.knowledge_id,
    )


def _compare_profiles(input_model: BaseModel) -> ToolExecutionOutput:
    request = cast(CompareChartProfilesInput, input_model)
    try:
        comparison = DOMAIN_KNOWLEDGE.compare_chart_profiles(request.profile_ids)
    except DomainKnowledgeError as error:
        raise _knowledge_problem(error) from error
    return ToolExecutionOutput(
        payload=comparison,
        summary=f"Compared {len(comparison.profile_ids)} reviewed chart profiles.",
    )


def _get_calculation(input_model: BaseModel) -> ToolExecutionOutput:
    request = cast(GetCalculationContractInput, input_model)
    try:
        contract = DOMAIN_KNOWLEDGE.get_calculation_contract(
            request.contract_id,
            contract_version=request.contract_version,
        )
    except DomainKnowledgeError as error:
        raise _knowledge_problem(error) from error
    return ToolExecutionOutput(
        payload=contract,
        summary=f"Returned reviewed calculation contract {contract.contract_id}.",
        output_handle=contract.contract_id,
    )


def _get_example(input_model: BaseModel) -> ToolExecutionOutput:
    request = cast(GetDomainExampleInput, input_model)
    try:
        example = DOMAIN_KNOWLEDGE.get_domain_example(request.example_id)
    except DomainKnowledgeError as error:
        raise _knowledge_problem(error) from error
    return ToolExecutionOutput(
        payload=example,
        summary=f"Returned reviewed domain example {example.example_id}.",
        output_handle=example.example_id,
    )


def register_domain_tools(gateway: ToolGateway) -> tuple[str, ...]:
    """Register the P0 knowledge tools and return their stable names."""

    registrations: tuple[
        tuple[str, str, str, type[BaseModel], type[BaseModel], ToolHandler], ...
    ] = (
        (
            "tool:list_chart_catalog",
            "list_chart_catalog",
            "List fig-agent's reviewed chart profiles and their public field-role contracts.",
            ListChartCatalogInput,
            ListChartCatalogOutput,
            _list_catalog,
        ),
        (
            "tool:get_chart_knowledge",
            "get_chart_knowledge",
            "Read the versioned, renderer-neutral knowledge card for one chart profile.",
            GetChartKnowledgeInput,
            ChartKnowledgeCard,
            _get_chart,
        ),
        (
            "tool:compare_chart_profiles",
            "compare_chart_profiles",
            "Compare reviewed data requirements and semantic boundaries for chart profiles.",
            CompareChartProfilesInput,
            ChartProfileComparison,
            _compare_profiles,
        ),
        (
            "tool:get_calculation_contract",
            "get_calculation_contract",
            "Read one frozen scientific calculation contract and its input/output semantics.",
            GetCalculationContractInput,
            CalculationContract,
            _get_calculation,
        ),
        (
            "tool:get_domain_example",
            "get_domain_example",
            "Read a reviewed minimal, near-miss, or invalid example by stable identifier.",
            GetDomainExampleInput,
            DomainExample,
            _get_example,
        ),
    )
    names: list[str] = []
    for contract_id, tool_name, description, input_model, output_model, handler in registrations:
        gateway.register(
            contract_id=contract_id,
            contract_version=1,
            tool_name=tool_name,
            description=description,
            permission_phase="p0_read",
            side_effect="none",
            allowed_task_states=_READ_STATES,
            input_model=input_model,
            output_model=output_model,
            cost_class="cheap",
            timeout_ms=5_000,
            max_disclosed_scalars=0,
            uses_origin=False,
            handler=handler,
        )
        names.append(tool_name)
    return tuple(names)
