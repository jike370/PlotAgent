/* Reviewed Origin 2024 bridge for T1 visual properties that have no
 * point-valued LabTalk setter.  The public UI exposes symbol edge width in
 * points only after "Scale by Symbol Size" is disabled; Set -kh otherwise
 * writes a percentage and silently rounds fractional values.
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

static int _plotagent_visual_plot(
    string graph_name,
    int layer_index,
    int plot_index,
    DataPlot& plot
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    plot = layer.DataPlots(plot_index - 1);
    return plot ? PA_OK : PA_BAD_PLOT;
}

static bool _plotagent_visual_node(TreeNode& format, int theme_id, TreeNode& node)
{
    return octree_get_node_by_id(&format, &node, theme_id, true);
}

int plotagent_set_symbol_edge_width(
    string graph_name,
    int layer_index,
    int plot_index,
    double width_points
)
{
    if (width_points < 0)
        return PA_BAD_FORMAT;
    DataPlot plot;
    int status = _plotagent_visual_plot(graph_name, layer_index, plot_index, plot);
    if (status != PA_OK)
        return status;
    /* Origin 2024's installed theme dictionary names the two alternatives:
     *   EdgeWidth    -> "Edge Width(%)" -> OTID 0x0094
     *   EdgeWidthVal -> "Edge Width"    -> OTID 0x09B3
     * A minimal tree is required because the inactive fixed-width node is not
     * returned by GetFormat.  UpdateThemeIDs resolves the installed mapping.
     */
    Tree format;
    format.Root.Symbol.EdgeWidthVal.dVal = width_points;
    if (plot.UpdateThemeIDs(format.Root) != PA_OK)
        return PA_MISSING_NODE;
    TreeNode edge_width;
    if (!_plotagent_visual_node(format, OTID_CURVE_SYMBOL_EDGE_WIDTH, edge_width))
        return PA_MISSING_NODE;
    return plot.ApplyFormat(format, true, true) ? PA_OK : PA_APPLY_FAILED;
}

double plotagent_visual_value(
    string graph_name,
    int layer_index,
    int plot_index,
    int theme_id,
    int numeric_type
)
{
    DataPlot plot;
    if (_plotagent_visual_plot(graph_name, layer_index, plot_index, plot) != PA_OK)
        return NANUM;
    TreeNode format = plot.GetFormat(FPB_ALL, FOB_ALL, true, false);
    if (!format)
        return NANUM;
    TreeNode node;
    if (!_plotagent_visual_node(format, theme_id, node))
        return NANUM;
    return numeric_type == 0 ? node.nVal : node.dVal;
}

int plotagent_set_color_scale_title(
    string graph_name,
    int layer_index,
    string title_text
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    Tree format;
    format = layer.GetFormat(FPB_ALL, FOB_ALL, true, false);
    if (!format)
        return PA_BAD_FORMAT;
    TreeNode title;
    title = format.Root.Page.Layers.All.Spectrums.All.DimAxes.DimAxis2.NewAxes.All.Title;
    if (!title)
        return PA_MISSING_NODE;
    TreeNode show = title.GetNode("Show");
    TreeNode text = title.GetNode("Text");
    if (!show || !text)
        return PA_MISSING_NODE;
    show.nVal = 1;
    text.strVal = title_text;
    return layer.ApplyFormat(format, true, false) ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_read_color_scale_title(
    string graph_name,
    int layer_index
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    Tree format;
    format = layer.GetFormat(FPB_ALL, FOB_ALL, true, false);
    if (!format)
        return PA_BAD_FORMAT;
    TreeNode title;
    title = format.Root.Page.Layers.All.Spectrums.All.DimAxes.DimAxis2.NewAxes.All.Title;
    if (!title)
        return PA_MISSING_NODE;
    TreeNode show = title.GetNode("Show");
    TreeNode text = title.GetNode("Text");
    if (!show || !text)
        return PA_MISSING_NODE;
    if (!LT_set_str("__PAT1CSTITLEOBS$", text.strVal))
        return PA_BAD_FORMAT;
    if (!LT_set_var("__PAT1CSTITLESHOW", show.nVal))
        return PA_BAD_FORMAT;
    return PA_OK;
}
