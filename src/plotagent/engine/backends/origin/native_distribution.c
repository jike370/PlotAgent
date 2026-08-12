/* Reviewed Origin 2024 native distribution-format bridge.
 *
 * Python's OriginExt DataPlot.GetTheme() can return an empty tree for native
 * PID 206/219 plots. These histogram/box computation settings belong to the
 * GraphLayer format tree; this bridge exposes only the pinned fields needed
 * by PlotAgent's K13/K14/K15 contracts and reads them back by their Origin
 * 2024 theme IDs.
 */

#include <Origin.h>
#include <OCTreeUtils.h>
#include <..\originlab\okThemeID.h>

#pragma labtalk(2)

#define PA_OK 0
#define PA_BAD_PAGE -1
#define PA_BAD_LAYER -2
#define PA_BAD_PLOT -3
#define PA_BAD_FORMAT -4
#define PA_MISSING_NODE -5
#define PA_APPLY_FAILED -6

static int _plotagent_distribution_layer(
    string graph_name,
    int plot_index,
    GraphLayer& layer
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    layer = page.Layers(0);
    if (!layer)
        return PA_BAD_LAYER;
    DataPlot plot = layer.DataPlots(plot_index - 1);
    if (!plot)
        return PA_BAD_PLOT;
    return PA_OK;
}

static bool _plotagent_distribution_node(TreeNode& format, int theme_id, TreeNode& node)
{
    return octree_get_node_by_id(&format, &node, theme_id, true);
}

static int _plotagent_distribution_set_int(
    TreeNode& format,
    int theme_id,
    int value
)
{
    TreeNode node;
    if (!_plotagent_distribution_node(format, theme_id, node))
        return PA_MISSING_NODE;
    node.nVal = value;
    return PA_OK;
}

static int _plotagent_distribution_set_double(
    TreeNode& format,
    int theme_id,
    double value
)
{
    TreeNode node;
    if (!_plotagent_distribution_node(format, theme_id, node))
        return PA_MISSING_NODE;
    node.dVal = value;
    return PA_OK;
}

int plotagent_configure_distribution(
    string graph_name,
    int plot_index,
    int profile_id,
    double bandwidth = 0
)
{
    GraphLayer layer;
    int status = _plotagent_distribution_layer(graph_name, plot_index, layer);
    if (status != PA_OK)
        return status;

    TreeNode format = layer.GetFormat(FPB_ALL, FOB_ALL, true, true);
    if (!format)
        return PA_BAD_FORMAT;

    if (profile_id == 13)
    {
        // OriginC/System/OC_const.h: Box, 25/75, Outlier, coefficient 1.5.
        status = _plotagent_distribution_set_int(
            format, OTID_BOXCHART_INFO_BOX_TYPE, OKBC_HAS_BOX
        );
        if (status != PA_OK)
            return status;
        status = _plotagent_distribution_set_int(
            format, OTID_BOXCHART_INFO_BOX_RANGE, BCBT_25_75
        );
        if (status != PA_OK)
            return status;
        status = _plotagent_distribution_set_int(
            format, OTID_BOXCHART_INFO_BOX_WHISKER_RANGE, BCWT_OUTLIER
        );
        if (status != PA_OK)
            return status;
        status = _plotagent_distribution_set_double(
            format, OTID_BOXCHART_INFO_BOX_WHISKER_COEFF, 1.5
        );
        if (status != PA_OK)
            return status;
        status = _plotagent_distribution_set_int(
            format, OTID_BOXCHART_INFO_BOX_HAS_OUTLIERS, 1
        );
        if (status != PA_OK)
            return status;
    }
    else if (profile_id == 14)
    {
        if (bandwidth <= 0)
            return PA_MISSING_NODE;
        status = _plotagent_distribution_set_int(
            format,
            OTID_BOXCHART_INFO_DIST_CURVE_TYPE,
            OKBC_HISTOGRAM_KERNEL_SMOOTH_CURVE
        );
        if (status != PA_OK)
            return status;
        // CurveScale is the Distribution-tab "Scale to Maximum (%)" value.
        // Violin.otpu already supplies the symmetric distribution geometry;
        // keep the official 100% width instead of shrinking it to 1%.
        status = _plotagent_distribution_set_int(
            format, OTID_BOXCHART_INFO_DIST_CURVE_SCALE, 100
        );
        if (status != PA_OK)
            return status;
        // Distribution tab order: Count=0, Width=1, Area=2.
        status = _plotagent_distribution_set_int(
            format, OTID_BOXCHART_INFO_DIST_SCALE_TYPE, 1
        );
        if (status != PA_OK)
            return status;
        // report_utils.c treats any negative selector as an explicit custom
        // bandwidth and consumes the absolute value from BandwidthFactor.
        status = _plotagent_distribution_set_int(
            format, OTID_BOXCHART_INFO_DIST_KERNEL_SMOOTH_BANDWIDTH, -1
        );
        if (status != PA_OK)
            return status;
        status = _plotagent_distribution_set_double(
            format,
            OTID_BOXCHART_INFO_DIST_KERNEL_SMOOTH_BANDWIDTH_FACTOR,
            bandwidth
        );
        if (status != PA_OK)
            return status;
        status = _plotagent_distribution_set_double(
            format, OTID_BOXCHART_INFO_DIST_KERNEL_SMOOTH_EXTEND, 0
        );
        if (status != PA_OK)
            return status;
    }
    else if (profile_id == 15)
    {
        status = _plotagent_distribution_set_int(
            format,
            OTID_BOXCHART_INFO_DATA_HEIGHT_TYPE,
            OKBC_DATA_HEIGHT_TYPE_COUNT
        );
        if (status != PA_OK)
            return status;
    }
    else
    {
        return PA_BAD_PLOT;
    }

    return layer.ApplyFormat(format, true, true) ? PA_OK : PA_APPLY_FAILED;
}

double plotagent_distribution_value(
    string graph_name,
    int plot_index,
    int theme_id,
    int numeric_type
)
{
    GraphLayer layer;
    if (_plotagent_distribution_layer(graph_name, plot_index, layer) != PA_OK)
        return NANUM;
    TreeNode format = layer.GetFormat(FPB_ALL, FOB_ALL, true, true);
    if (!format)
        return NANUM;
    TreeNode node;
    if (!_plotagent_distribution_node(format, theme_id, node))
        return NANUM;
    return numeric_type == 0 ? node.nVal : node.dVal;
}
