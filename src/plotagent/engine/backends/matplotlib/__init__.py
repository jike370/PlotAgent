"""Independent Matplotlib renderers for Agent Native profiles."""

from .area import K18AreaRenderer
from .backend import MatplotlibBackend
from .bubble import K04BubbleRenderer
from .calculated_distribution import K15HistogramRenderer, K16DensityRenderer
from .column import K08ColumnRenderer
from .column_family import (
    K09GroupedColumnRenderer,
    K10StackedColumnRenderer,
    K11PercentStackRenderer,
)
from .composite import K25CompositeRenderer
from .confusion_matrix import S61ConfusionRenderer
from .contour import K22ContourRenderer
from .correlation_matrix import K21CorrelationMatrixRenderer
from .distribution import K12StripRenderer, K13BoxRenderer, K14ViolinRenderer, X05BeeswarmRenderer
from .drop_line import X02DropLineRenderer
from .dual_y import X23DualYRenderer
from .error_band import K07ErrorBandRenderer
from .facet import K24FacetRenderer
from .floating_interval import X09FloatingIntervalRenderer
from .heatmap import K20HeatmapRenderer
from .line import K01LineRenderer
from .line_symbol import K02LineSymbolRenderer
from .nyquist import S34NyquistRenderer
from .point_error import K06PointErrorRenderer
from .population_pyramid import X13PopulationPyramidRenderer
from .scatter import K03ScatterRenderer
from .special_t1 import (
    X24ParetoRenderer,
    X35DualYColumnRenderer,
    X36DualYColumnLineRenderer,
    X38OffsetStackRenderer,
)
from .special_t2 import (
    S01SurvivalRenderer,
    S21ForestRenderer,
)
from .time_series import K19TimeSeriesRenderer
from .wide_series import X03LollipopRenderer, X39LineSeriesRenderer, X40BeforeAfterRenderer

__all__ = [
    "K01LineRenderer",
    "K02LineSymbolRenderer",
    "K03ScatterRenderer",
    "K04BubbleRenderer",
    "K06PointErrorRenderer",
    "K07ErrorBandRenderer",
    "K08ColumnRenderer",
    "K09GroupedColumnRenderer",
    "K10StackedColumnRenderer",
    "K11PercentStackRenderer",
    "K12StripRenderer",
    "K13BoxRenderer",
    "K14ViolinRenderer",
    "K15HistogramRenderer",
    "K16DensityRenderer",
    "K18AreaRenderer",
    "K19TimeSeriesRenderer",
    "K20HeatmapRenderer",
    "K21CorrelationMatrixRenderer",
    "K22ContourRenderer",
    "K24FacetRenderer",
    "K25CompositeRenderer",
    "MatplotlibBackend",
    "S01SurvivalRenderer",
    "S21ForestRenderer",
    "S34NyquistRenderer",
    "S61ConfusionRenderer",
    "X02DropLineRenderer",
    "X03LollipopRenderer",
    "X05BeeswarmRenderer",
    "X09FloatingIntervalRenderer",
    "X13PopulationPyramidRenderer",
    "X23DualYRenderer",
    "X24ParetoRenderer",
    "X35DualYColumnRenderer",
    "X36DualYColumnLineRenderer",
    "X38OffsetStackRenderer",
    "X39LineSeriesRenderer",
    "X40BeforeAfterRenderer",
]
