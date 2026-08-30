"""Auditable product defaults shared by plotting backends.

Profile renderers own geometry and may declare a necessary exception.  These
values are the product fallback when neither the profile nor an explicit user
action supplies a style.  Keeping them in one module avoids silently inheriting
unrelated Matplotlib and Origin template defaults.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProductTypography:
    title_font_size_pt: float
    axis_title_font_size_pt: float
    tick_font_size_pt: float
    legend_font_size_pt: float

    def matplotlib_rc(self) -> dict[str, float]:
        return {
            "axes.titlesize": self.title_font_size_pt,
            "axes.labelsize": self.axis_title_font_size_pt,
            "xtick.labelsize": self.tick_font_size_pt,
            "ytick.labelsize": self.tick_font_size_pt,
            "legend.fontsize": self.legend_font_size_pt,
            "legend.title_fontsize": self.legend_font_size_pt,
        }


PRODUCT_TYPOGRAPHY = ProductTypography(
    title_font_size_pt=10.0,
    axis_title_font_size_pt=9.0,
    tick_font_size_pt=8.0,
    legend_font_size_pt=8.0,
)

# X35/X36 expose two semantic series across independent Y axes.  Their default
# colors are part of the product contract, not backend-local suggestions: a
# request without SetSeriesStyle must render the same two colors in the preview
# and the editable Origin project.
DUAL_Y_SERIES_COLORS = ("#1676D2", "#D97800")

# Other multi-series renderers may reuse the same ordered product palette while
# retaining profile-specific geometry and explicit user overrides.
PRODUCT_SERIES_PALETTE = (
    *DUAL_Y_SERIES_COLORS,
    "#299764",
    "#C53D4D",
    "#7656B5",
    "#008A99",
)
