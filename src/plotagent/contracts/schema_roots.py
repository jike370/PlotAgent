"""Named RootModels for discriminated unions exported as standalone schemas."""

from pydantic import RootModel

from plotagent.contracts.agent_context import ContextEnvelope
from plotagent.contracts.calculations import PlotCalculationResult, PlotCalculationSpec
from plotagent.contracts.datasets import PreparationSpec
from plotagent.contracts.decisions import AgentDecision
from plotagent.contracts.plots import PlotPatch


class PreparationSpecContract(RootModel[PreparationSpec]):
    pass


class PlotCalculationSpecContract(RootModel[PlotCalculationSpec]):
    pass


class PlotCalculationResultContract(RootModel[PlotCalculationResult]):
    pass


class PlotPatchContract(RootModel[PlotPatch]):
    pass


class AgentDecisionContract(RootModel[AgentDecision]):
    pass


class ContextEnvelopeContract(RootModel[ContextEnvelope]):
    pass
