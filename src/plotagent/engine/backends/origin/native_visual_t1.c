/* Reviewed Origin 2024 bridge for shared T1 visual properties. */

#include <Origin.h>

#pragma labtalk(2)

#define PA_OK 0
#define PA_BAD_PAGE -1
#define PA_BAD_LAYER -2
#define PA_BAD_PLOT -3
#define PA_BAD_FORMAT -4
#define PA_MISSING_NODE -5
#define PA_APPLY_FAILED -6
#define PA_MISSING_SPECTRUM -51
#define PA_MISSING_AUTO_LABELS -52
#define PA_MISSING_TICK_LABELS -53
#define PA_MISSING_TICK_FORMAT -54
#define PA_OTID_AXIS_LABEL_TYPE 0x0115
#define PA_OTID_AXIS_LABEL_NUMERIC 0x0116
#define PA_OTID_AXIS_LABEL_CUSTOM_FORMAT 0x05bb
#define PA_OTID_AXIS_LABEL_MANUAL_DEC 0x05af
#define PA_OTID_AXIS_LABEL_IS_TABLE 0x0691
#define PA_OTID_AXIS_LABEL_TABLE_DESIGN 0x06bd
#define PA_OTID_AXIS_LABEL_HIDE_ROW 0x06de

static TreeNode _plotagent_direct_child_by_id(TreeNode& parent, int theme_id)
{
    foreach(TreeNode child in parent.Children)
    {
        if (child.ID == theme_id)
            return child;
    }
    TreeNode missing;
    return missing;
}

static TreeNode _plotagent_axis_label_node(Tree& format, int axis_code)
{
    if (axis_code == 0)
        return format.Root.Labels.BottomLabels;
    if (axis_code == 1)
        return format.Root.Labels.LeftLabels;
    if (axis_code == 2)
        return format.Root.Labels.TopLabels;
    if (axis_code == 3)
        return format.Root.Labels.RightLabels;
    TreeNode missing;
    return missing;
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

int plotagent_set_color_scale_anchor(
    string graph_name,
    int layer_index,
    int anchor_code
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    GraphObject scale = layer.GraphObjects("SPECTRUM1");
    if (!scale)
        return PA_MISSING_NODE;
    Tree format;
    format = scale.GetFormat(FPB_ALL, FOB_ALL, true, true);
    if (!format)
        return PA_BAD_FORMAT;
    TreeNode arrangement = format.Root.Layout.GetNode("Arrangement");
    if (!arrangement)
        return PA_MISSING_NODE;
    if (anchor_code == 0)
        arrangement.nVal = SPECTRUM_Arrangement_Vertical;
    else if (anchor_code == 1)
        arrangement.nVal = SPECTRUM_Arrangement_Horizontal;
    else
        return PA_MISSING_NODE;
    if (scale.UpdateThemeIDs(format.Root) != 0)
        return PA_BAD_FORMAT;
    if (!scale.ApplyFormat(format, true, true, true))
        return PA_APPLY_FAILED;

    int left, top, right, bottom;
    if (!get_layer_rect_page_units(layer, left, top, right, bottom))
        return PA_BAD_FORMAT;
    const int side_gap = 120;
    const int bottom_gap = 300;
    const int compact_thickness = 300;
    scale.Attach = ATTACH_TO_PAGE;
    if (anchor_code == 0)
    {
        scale.Width = compact_thickness;
        scale.Height = bottom - top;
        scale.Left = right + side_gap;
        scale.Top = top;
    }
    else
    {
        scale.Width = right - left;
        scale.Height = compact_thickness;
        scale.Left = left;
        scale.Top = bottom + bottom_gap;
    }
    return PA_OK;
}

int plotagent_read_color_scale_anchor(
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
    GraphObject scale = layer.GraphObjects("SPECTRUM1");
    if (!scale)
        return PA_MISSING_NODE;
    Tree format;
    format = scale.GetFormat(FPB_ALL, FOB_ALL, true, true);
    if (!format)
        return PA_BAD_FORMAT;
    TreeNode arrangement = format.Root.Layout.GetNode("Arrangement");
    if (!arrangement)
        return PA_MISSING_NODE;
    int left, top, right, bottom;
    if (!get_layer_rect_page_units(layer, left, top, right, bottom))
        return PA_BAD_FORMAT;
    if (!LT_set_var("__PAT1CSARRANGEMENT", arrangement.nVal)
        || !LT_set_var("__PAT1CSATTACH", scale.Attach)
        || !LT_set_var("__PAT1CSLEFT", scale.Left)
        || !LT_set_var("__PAT1CSTOP", scale.Top)
        || !LT_set_var("__PAT1CSWIDTH", scale.Width)
        || !LT_set_var("__PAT1CSHEIGHT", scale.Height)
        || !LT_set_var("__PAT1LAYERLEFT", left)
        || !LT_set_var("__PAT1LAYERTOP", top)
        || !LT_set_var("__PAT1LAYERRIGHT", right)
        || !LT_set_var("__PAT1LAYERBOTTOM", bottom))
        return PA_BAD_FORMAT;
    return PA_OK;
}

int plotagent_set_color_scale_tick_format(
    string graph_name,
    int layer_index,
    int format_code
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    if (!layer.GraphObjects("SPECTRUM1"))
        return PA_MISSING_SPECTRUM;
    Tree format;
    format = layer.GetFormat(FPB_ALL, FOB_ALL, true, false);
    if (!format)
        return PA_BAD_FORMAT;

    TreeNode spectrum = format.Root.Page.Layers.All.Spectrums.All;
    if (!spectrum)
        return PA_MISSING_SPECTRUM;
    TreeNode automatic = spectrum.Extends.GetNode("LabelsDisplayAuto");
    TreeNode labels = spectrum.DimAxes.DimAxis2.NewAxes.All.Labels.All;
    if (!automatic)
        return PA_MISSING_AUTO_LABELS;
    if (!labels)
        return PA_MISSING_TICK_LABELS;
    TreeNode type = labels.GetNode("Type");
    TreeNode numeric = labels.GetNode("NumericFormat");
    TreeNode custom = labels.GetNode("CustomFormat");
    if (!type)
        type = labels.AddNode("Type", PA_OTID_AXIS_LABEL_TYPE);
    if (!numeric)
        numeric = labels.AddNode("NumericFormat", PA_OTID_AXIS_LABEL_NUMERIC);
    if (!custom)
        custom = labels.AddNode("CustomFormat", PA_OTID_AXIS_LABEL_CUSTOM_FORMAT);
    if (!type || !numeric || !custom)
        return PA_MISSING_TICK_FORMAT;

    /* Origin 2024's tick-label Type enum uses 0 for numeric. */
    type.nVal = 0;
    automatic.nVal = format_code == 0 ? 1 : 0;
    if (format_code == 0)
    {
        /* Keep the template's numeric format while automatic display is enabled. */
    }
    else if (format_code == 1)
    {
        /* Match the public decimal semantic: ordinary decimal notation with
           enough significant digits to avoid rounding adjacent levels into
           duplicate labels. */
        numeric.nVal = LABELS_NUM_CUSTOM;
        custom.strVal = "*6";
    }
    else if (format_code == 2)
    {
        numeric.nVal = LABELS_NUM_SCI_1E3;
        custom.strVal = "";
    }
    else if (format_code == 3)
    {
        numeric.nVal = LABELS_NUM_CUSTOM;
        custom.strVal = "*3%";
    }
    else
        return PA_MISSING_NODE;

    return layer.ApplyFormat(format, true, false) ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_set_color_scale_typography(
    string graph_name,
    int layer_index,
    double title_font_size,
    double tick_font_size
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
    TreeNode spectrum = format.Root.Page.Layers.All.Spectrums.All;
    TreeNode title_size = spectrum.DimAxes.DimAxis2.NewAxes.All.Title.Font.GetNode("Size");
    TreeNode tick_size = spectrum.DimAxes.DimAxis2.NewAxes.All.Labels.All.Font.GetNode("Size");
    if (!title_size || !tick_size)
        return PA_MISSING_NODE;
    title_size.dVal = title_font_size;
    tick_size.dVal = tick_font_size;
    return layer.ApplyFormat(format, true, false) ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_read_color_scale_typography(string graph_name, int layer_index)
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
    TreeNode spectrum = format.Root.Page.Layers.All.Spectrums.All;
    TreeNode title_size = spectrum.DimAxes.DimAxis2.NewAxes.All.Title.Font.GetNode("Size");
    TreeNode tick_size = spectrum.DimAxes.DimAxis2.NewAxes.All.Labels.All.Font.GetNode("Size");
    if (!title_size || !tick_size)
        return PA_MISSING_NODE;
    if (!LT_set_var("__PAT1CSTITLEFONTSIZE", title_size.dVal)
        || !LT_set_var("__PAT1CSTICKFONTSIZE", tick_size.dVal))
        return PA_BAD_FORMAT;
    return PA_OK;
}

int plotagent_set_k22_contour_lines_visible(
    string graph_name,
    int layer_index,
    int plot_index,
    int visible
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    DataPlot plot = layer.DataPlots(plot_index - 1);
    if (!plot)
        return PA_BAD_PLOT;
    Tree colormap;
    if (!plot.GetColormap(colormap))
        return PA_BAD_FORMAT;
    vector widths;
    if (!colormap.GetValue(widths, "LineWidths", true, true)
        || widths.GetSize() < 1)
        return PA_MISSING_NODE;
    widths = visible ? 0.5 : 0;
    if (!colormap.SetValue(widths, "LineWidths", true, true)
        || !colormap.SetValue(visible ? 0.5 : 0.0, "AboveLineWidth", true, true)
        || !colormap.SetValue(visible ? 1 : 0, "MajorLines", true, true))
        return PA_MISSING_NODE;
    return plot.SetColormap(colormap) ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_read_k22_contour_lines(
    string graph_name,
    int layer_index,
    int plot_index
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    DataPlot plot = layer.DataPlots(plot_index - 1);
    if (!plot)
        return PA_BAD_PLOT;
    Tree colormap;
    if (!plot.GetColormap(colormap))
        return PA_BAD_FORMAT;
    vector widths;
    if (!colormap.GetValue(widths, "LineWidths", true, true)
        || widths.GetSize() < 1)
        return PA_MISSING_NODE;
    int interval_count = widths.GetSize();
    if (interval_count < 1)
        return PA_MISSING_NODE;
    int visible_count = 0;
    for (int index = 0; index < widths.GetSize(); index++)
        if (widths[index] > 0)
            visible_count++;
    double above_width = 0;
    if (!colormap.GetValue(above_width, "AboveLineWidth", true, true))
        return PA_MISSING_NODE;
    if (!LT_set_var("__PAT1K22LINECOUNT", interval_count)
        || !LT_set_var("__PAT1K22LINESHOW", visible_count)
        || !LT_set_var("__PAT1K22ABOVELINE", above_width > 0 ? 1 : 0))
        return PA_BAD_FORMAT;
    return PA_OK;
}

int plotagent_read_color_scale_tick_format(
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
    if (!layer.GraphObjects("SPECTRUM1"))
        return PA_MISSING_SPECTRUM;
    Tree format;
    format = layer.GetFormat(FPB_ALL, FOB_ALL, true, false);
    if (!format)
        return PA_BAD_FORMAT;

    TreeNode spectrum = format.Root.Page.Layers.All.Spectrums.All;
    if (!spectrum)
        return PA_MISSING_SPECTRUM;
    TreeNode automatic = spectrum.Extends.GetNode("LabelsDisplayAuto");
    TreeNode labels = spectrum.DimAxes.DimAxis2.NewAxes.All.Labels.All;
    if (!automatic)
        return PA_MISSING_AUTO_LABELS;
    if (!labels)
        return PA_MISSING_TICK_LABELS;
    TreeNode type = labels.GetNode("Type");
    TreeNode numeric = labels.GetNode("NumericFormat");
    TreeNode custom = labels.GetNode("CustomFormat");
    if (!type || !numeric)
        return PA_MISSING_TICK_FORMAT;
    string custom_format = custom ? custom.strVal : "";
    if (!LT_set_var("__PAT1CSTICKAUTO", automatic.nVal)
        || !LT_set_var("__PAT1CSTICKTYPE", type.nVal)
        || !LT_set_var("__PAT1CSTICKNUM", numeric.nVal)
        || !LT_set_str("__PAT1CSTICKCUSTOM$", custom_format))
        return PA_BAD_FORMAT;
    return PA_OK;
}

int plotagent_set_axis_line_show(
    string graph_name,
    int layer_index,
    int axis_code,
    int show
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    Tree format;
    format = layer.GetFormat(FPB_SHOW, FOB_AXIS, true, true);
    if (!format)
        return PA_BAD_FORMAT;
    TreeNode ticks;
    if (axis_code == 0)
        ticks = format.Root.Axes.X.Ticks.GetNode("BottomTicks");
    else if (axis_code == 1)
        ticks = format.Root.Axes.Y.Ticks.GetNode("LeftTicks");
    else if (axis_code == 2)
        ticks = format.Root.Axes.X.Ticks.GetNode("TopTicks");
    else if (axis_code == 3)
        ticks = format.Root.Axes.Y.Ticks.GetNode("RightTicks");
    else
        return PA_MISSING_NODE;
    if (!ticks)
        return PA_MISSING_NODE;
    TreeNode visible = ticks.GetNode("Show");
    if (!visible)
        return PA_MISSING_NODE;
    visible.nVal = show ? 1 : 0;
    layer.UpdateThemeIDs(format.Root);
    return layer.ApplyFormat(format, true, true, true) ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_read_axis_line_show(
    string graph_name,
    int layer_index,
    int axis_code
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    Tree format;
    format = layer.GetFormat(FPB_SHOW, FOB_AXIS, true, true);
    if (!format)
        return PA_BAD_FORMAT;
    TreeNode ticks;
    if (axis_code == 0)
        ticks = format.Root.Axes.X.Ticks.GetNode("BottomTicks");
    else if (axis_code == 1)
        ticks = format.Root.Axes.Y.Ticks.GetNode("LeftTicks");
    else if (axis_code == 2)
        ticks = format.Root.Axes.X.Ticks.GetNode("TopTicks");
    else if (axis_code == 3)
        ticks = format.Root.Axes.Y.Ticks.GetNode("RightTicks");
    else
        return PA_MISSING_NODE;
    if (!ticks)
        return PA_MISSING_NODE;
    TreeNode visible = ticks.GetNode("Show");
    if (!visible)
        return PA_MISSING_NODE;
    if (!LT_set_var("__PAT1AXISSHOW", visible.nVal))
        return PA_BAD_FORMAT;
    return PA_OK;
}

int plotagent_set_axis_tick_font_size(
    string graph_name,
    int layer_index,
    int axis_code,
    double font_size_pt
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    Axis axis = axis_code == 0 || axis_code == 2 ? layer.XAxis : layer.YAxis;
    if (!axis)
        return PA_BAD_LAYER;
    Tree format;
    format = axis.GetFormat(FPB_ALL, FOB_AXIS_LABELS, true, true);
    if (!format)
        return PA_BAD_FORMAT;
    TreeNode label = _plotagent_axis_label_node(format, axis_code);
    if (!label || !label.Font || !label.Font.Size)
        return PA_MISSING_NODE;
    label.Font.Size.dVal = font_size_pt;
    if (axis.UpdateThemeIDs(format.Root, "Error", "Unknown tag") != 0)
        return PA_BAD_FORMAT;
    return axis.ApplyFormat(format, true, true, true) ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_read_axis_tick_font_size(
    string graph_name,
    int layer_index,
    int axis_code
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    Axis axis = axis_code == 0 || axis_code == 2 ? layer.XAxis : layer.YAxis;
    if (!axis)
        return PA_BAD_LAYER;
    Tree format;
    format = axis.GetFormat(FPB_ALL, FOB_AXIS_LABELS, true, true);
    if (!format)
        return PA_BAD_FORMAT;
    TreeNode label = _plotagent_axis_label_node(format, axis_code);
    if (!label || !label.Font || !label.Font.Size)
        return PA_MISSING_NODE;
    if (!LT_set_var("__PAT1AXISTICKSIZE", label.Font.Size.dVal))
        return PA_BAD_FORMAT;
    return PA_OK;
}

int plotagent_configure_k09_axis_labels(
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
    Axis axis = layer.XAxis;
    if (!axis)
        return PA_BAD_LAYER;
    Tree format;
    format = axis.GetFormat(FPB_ALL, FOB_AXIS_LABELS, true, true);
    if (!format)
        return PA_BAD_FORMAT;
    TreeNode label = format.Root.Labels.BottomLabels;
    if (!label || !label.Levels || !label.Levels.Level1)
        return PA_MISSING_NODE;
    TreeNode is_table = _plotagent_direct_child_by_id(
        label,
        PA_OTID_AXIS_LABEL_IS_TABLE
    );
    TreeNode table_design = _plotagent_direct_child_by_id(
        label,
        PA_OTID_AXIS_LABEL_TABLE_DESIGN
    );
    if (!is_table || !table_design)
        return PA_MISSING_NODE;
    TreeNode level = label.Levels.Level1;
    if (!level.HideRow)
        level.HideRow.ID = PA_OTID_AXIS_LABEL_HIDE_ROW;
    level.HideRow.nVal = 1;
    is_table.nVal = 1;
    table_design.nVal = 0;
    if (axis.UpdateThemeIDs(format.Root, "Error", "Unknown tag") != 0)
        return PA_BAD_FORMAT;
    return axis.ApplyFormat(format, true, true, true) ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_read_k09_axis_labels(
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
    Axis axis = layer.XAxis;
    if (!axis)
        return PA_BAD_LAYER;
    Tree format;
    format = axis.GetFormat(FPB_ALL, FOB_AXIS_LABELS, true, true);
    if (!format)
        return PA_BAD_FORMAT;
    TreeNode label = format.Root.Labels.BottomLabels;
    if (!label || !label.Levels || !label.Levels.Level1)
        return PA_MISSING_NODE;
    TreeNode is_table = _plotagent_direct_child_by_id(
        label,
        PA_OTID_AXIS_LABEL_IS_TABLE
    );
    TreeNode table_design = _plotagent_direct_child_by_id(
        label,
        PA_OTID_AXIS_LABEL_TABLE_DESIGN
    );
    TreeNode level = label.Levels.Level1;
    if (!is_table || !table_design || !level.HideRow)
        return PA_MISSING_NODE;
    if (!LT_set_var("__PAT1K09ISTABLE", is_table.nVal)
        || !LT_set_var("__PAT1K09TABLEDESIGN", table_design.nVal)
        || !LT_set_var("__PAT1K09LEVEL1HIDDEN", level.HideRow.nVal))
        return PA_BAD_FORMAT;
    return PA_OK;
}

int plotagent_remove_graph_object(
    string graph_name,
    int layer_index,
    string object_name
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    GraphObject object = layer.GraphObjects(object_name);
    if (!object)
        return PA_OK;
    return object.Destroy() ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_set_scale_arrow(
    string graph_name,
    int layer_index,
    string arrow_name,
    double x0,
    double y0,
    double x1,
    double y1
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;

    GraphObject existing = layer.GraphObjects(arrow_name);
    if (existing && !existing.Destroy())
        return PA_APPLY_FAILED;

    GraphObject arrow = layer.CreateGraphObject(GROT_LINE, arrow_name);
    if (!arrow)
        return PA_MISSING_NODE;
    arrow.Attach = ATTACH_TO_SCALE;

    vector x_values(2), y_values(2);
    x_values[0] = x0;
    x_values[1] = x1;
    y_values[0] = y0;
    y_values[1] = y1;
    Tree format;
    /* Origin's documented scale unit keeps the vertices as axis values. */
    format.Root.Dimension.Units.nVal = 5;
    format.Root.Data.X.dVals = x_values;
    format.Root.Data.Y.dVals = y_values;
    format.Root.Arrow.Begin.Style.nVal = 0;
    format.Root.Arrow.End.Style.nVal = 1;
    if (arrow.UpdateThemeIDs(format.Root) != 0)
        return PA_BAD_FORMAT;
    return arrow.ApplyFormat(format, true, true) ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_read_scale_arrow(
    string graph_name,
    int layer_index,
    string arrow_name
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    GraphObject arrow = layer.GraphObjects(arrow_name);
    if (!arrow)
        return PA_MISSING_NODE;
    Tree format;
    format = arrow.GetFormat(FPB_DATA, FOB_ALL, true, true);
    if (!format || !format.Root.Data.X || !format.Root.Data.Y)
        return PA_BAD_FORMAT;
    vector x_values, y_values;
    x_values = format.Root.Data.X.dVals;
    y_values = format.Root.Data.Y.dVals;
    if (x_values.GetSize() != 2 || y_values.GetSize() != 2)
        return PA_BAD_FORMAT;
    Tree style;
    style = arrow.GetFormat(FPB_OTHER, FOB_ALL, true, true);
    if (!style || !style.Root.Arrow.Begin.Style || !style.Root.Arrow.End.Style)
        return PA_BAD_FORMAT;
    if (!LT_set_var("__PAT1CALLATTACH", arrow.Attach)
        || !LT_set_var("__PAT1CALLX0", x_values[0])
        || !LT_set_var("__PAT1CALLY0", y_values[0])
        || !LT_set_var("__PAT1CALLX1", x_values[1])
        || !LT_set_var("__PAT1CALLY1", y_values[1])
        || !LT_set_var("__PAT1CALLBEGIN", style.Root.Arrow.Begin.Style.nVal)
        || !LT_set_var("__PAT1CALLEND", style.Root.Arrow.End.Style.nVal))
        return PA_BAD_FORMAT;
    return PA_OK;
}

int plotagent_set_scale_arrow_head(
    string graph_name,
    int layer_index,
    string arrow_name,
    int end_style
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    GraphObject arrow = layer.GraphObjects(arrow_name);
    if (!arrow)
        return PA_MISSING_NODE;
    Tree style;
    style.Root.Arrow.Begin.Style.nVal = 0;
    style.Root.Arrow.End.Style.nVal = end_style;
    if (arrow.UpdateThemeIDs(style.Root) != 0)
        return PA_BAD_FORMAT;
    return arrow.ApplyFormat(style, true, true) ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_set_k07_error_band_fill_transparency(
    string graph_name,
    int layer_index,
    double fill_transparency
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    /*
       ERRORBAND.OTP stores its visible band on the two Y-error DataPlots.
       Generic DataPlot transparency and Pattern.Border values can persist
       while the connected error-band renderer continues to paint the
       template's 50%% fill and automatic boundary.  OriginLab's documented
       Origin C route is DataPlot.GetFormat -> Pattern.Transparency, followed
       by UpdateThemeIDs/ApplyFormat.  Connected-line color and width use the
       documented LabTalk plot color/width commands and are read from the
       ErrorBar2D nodes below.
    */
    for (int plot_index = 1; plot_index <= 2; plot_index++)
    {
        DataPlot plot = layer.DataPlots(plot_index);
        if (!plot)
            return PA_MISSING_NODE;
        Tree format;
        format = plot.GetFormat(FPB_ALL, FOB_ALL, true, true);
        if (!format || !format.Root.Pattern || !format.Root.Pattern.Transparency
            || !format.Root.ErrorBar2D || !format.Root.ErrorBar2D.ConnectLineColor
            || !format.Root.ErrorBar2D.ConnectLineWidth)
            return PA_BAD_FORMAT;
        format.Root.Pattern.Transparency.dVal = fill_transparency;
        if (plot.UpdateThemeIDs(format.Root) != 0)
            return PA_BAD_FORMAT;
        if (!plot.ApplyFormat(format, true, true))
            return PA_APPLY_FAILED;
    }
    return PA_OK;
}

int plotagent_read_k07_error_band_style(string graph_name, int layer_index)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    for (int plot_index = 1; plot_index <= 2; plot_index++)
    {
        DataPlot plot = layer.DataPlots(plot_index);
        if (!plot)
            return PA_MISSING_NODE;
        Tree format;
        format = plot.GetFormat(FPB_ALL, FOB_ALL, true, true);
        if (!format || !format.Root.Pattern || !format.Root.Pattern.Transparency
            || !format.Root.ErrorBar2D || !format.Root.ErrorBar2D.ConnectLineColor
            || !format.Root.ErrorBar2D.ConnectLineWidth)
            return PA_BAD_FORMAT;
        if (plot_index == 1)
        {
            if (!LT_set_var("__PAT1K07FILLTRANS1", format.Root.Pattern.Transparency.dVal)
                || !LT_set_var("__PAT1K07LINECOLOR1",
                               format.Root.ErrorBar2D.ConnectLineColor.nVal)
                || !LT_set_var("__PAT1K07LINEWIDTH1",
                               format.Root.ErrorBar2D.ConnectLineWidth.dVal))
                return PA_BAD_FORMAT;
        }
        else
        {
            if (!LT_set_var("__PAT1K07FILLTRANS2", format.Root.Pattern.Transparency.dVal)
                || !LT_set_var("__PAT1K07LINECOLOR2",
                               format.Root.ErrorBar2D.ConnectLineColor.nVal)
                || !LT_set_var("__PAT1K07LINEWIDTH2",
                               format.Root.ErrorBar2D.ConnectLineWidth.dVal))
                return PA_BAD_FORMAT;
        }
    }
    return PA_OK;
}

int plotagent_set_k14_violin_style(
    string graph_name,
    int layer_index,
    int plot_index,
    int fill_color,
    double fill_transparency,
    int outline_color,
    double outline_width,
    int outline_style
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    DataPlot plot = layer.DataPlots(plot_index - 1);
    if (!plot)
        return PA_BAD_PLOT;

    /*
       PID 206 Violin stores two pattern branches. Generic -pfb/-pbc and
       OTID_CURVE_PATTERN_* lookup resolve the Above branch and can persist
       while the visible violin remains unchanged. The symmetric violin body
       is painted by Patterns.Below; its visible outline is the root Line,
       not Pattern.Border. Write those native owners explicitly.
    */
    Tree format;
    format = plot.GetFormat(FPB_ALL, FOB_ALL, true, true);
    if (!format || !format.Root.Patterns || !format.Root.Patterns.Below
        || !format.Root.Patterns.Below.Fill
        || !format.Root.Patterns.Below.Fill.FillColor
        || !format.Root.Patterns.Below.Transparency
        || !format.Root.Patterns.Below.TransparencyFillOnly
        || !format.Root.Patterns.Below.FollowLineTransparency
        || !format.Root.Color || !format.Root.Width || !format.Root.Style)
        return PA_BAD_FORMAT;
    format.Root.Patterns.Below.Fill.FillColor.nVal = fill_color;
    format.Root.Patterns.Below.Transparency.dVal = fill_transparency;
    format.Root.Patterns.Below.TransparencyFillOnly.nVal = 1;
    format.Root.Patterns.Below.FollowLineTransparency.nVal = 0;
    format.Root.Color.nVal = outline_color;
    format.Root.Width.dVal = outline_width;
    format.Root.Style.nVal = outline_style;
    if (plot.UpdateThemeIDs(format.Root) != 0)
        return PA_BAD_FORMAT;
    return plot.ApplyFormat(format, true, true) ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_read_k14_violin_style(
    string graph_name,
    int layer_index,
    int plot_index
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    DataPlot plot = layer.DataPlots(plot_index - 1);
    if (!plot)
        return PA_BAD_PLOT;
    Tree format;
    format = plot.GetFormat(FPB_ALL, FOB_ALL, true, true);
    if (!format || !format.Root.Patterns || !format.Root.Patterns.Below
        || !format.Root.Patterns.Below.Fill
        || !format.Root.Patterns.Below.Fill.FillColor
        || !format.Root.Patterns.Below.Transparency
        || !format.Root.Patterns.Below.TransparencyFillOnly
        || !format.Root.Patterns.Below.FollowLineTransparency
        || !format.Root.Color || !format.Root.Width || !format.Root.Style)
        return PA_BAD_FORMAT;
    if (!LT_set_var("__PAT1K14FILLCOLOR", format.Root.Patterns.Below.Fill.FillColor.nVal)
        || !LT_set_var("__PAT1K14FILLTRANS", format.Root.Patterns.Below.Transparency.dVal)
        || !LT_set_var(
            "__PAT1K14FILLONLY", format.Root.Patterns.Below.TransparencyFillOnly.nVal
        )
        || !LT_set_var(
            "__PAT1K14FOLLOWLINE", format.Root.Patterns.Below.FollowLineTransparency.nVal
        )
        || !LT_set_var("__PAT1K14LINECOLOR", format.Root.Color.nVal)
        || !LT_set_var("__PAT1K14LINEWIDTH", format.Root.Width.dVal)
        || !LT_set_var("__PAT1K14LINESTYLE", format.Root.Style.nVal))
        return PA_BAD_FORMAT;
    return PA_OK;
}

int plotagent_set_x09_group_fill_color(
    string graph_name,
    int layer_index,
    int fill_color
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    GroupPlot group = layer.Groups(0);
    if (!group || group.GetCount() < 2)
        return PA_MISSING_NODE;

    /*
       FLOATCOL is a dependent group: plot 1 is the starting boundary and
       plots 2..N paint the adjacent visible intervals.  Per-DataPlot -pfb
       values can read back successfully while the group increment list still
       owns the visible fill.  Write that native list directly, following
       OriginLab's documented GroupPlot BackgroundColor example.
    */
    vector<int> colors(group.GetCount());
    for (int index = 0; index < colors.GetSize(); index++)
        colors[index] = fill_color;
    group.Increment.BackgroundColor.nVals = colors;
    return PA_OK;
}

int plotagent_set_x09_group_fill_colors(
    string graph_name,
    int layer_index,
    int fill_color_1,
    int fill_color_2,
    int fill_color_3
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    GroupPlot group = layer.Groups(0);
    if (!group || group.GetCount() < 2 || group.GetCount() > 3)
        return PA_MISSING_NODE;

    vector<int> colors(group.GetCount());
    colors[0] = fill_color_1;
    colors[1] = fill_color_2;
    if (group.GetCount() == 3)
        colors[2] = fill_color_3;
    group.Increment.BackgroundColor.nVals = colors;
    return PA_OK;
}

int plotagent_read_x09_group_fill_colors(string graph_name, int layer_index)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    GroupPlot group = layer.Groups(0);
    if (!group || group.GetCount() < 2)
        return PA_MISSING_NODE;
    vector<int> colors;
    colors = group.Increment.BackgroundColor.nVals;
    if (colors.GetSize() < group.GetCount())
        return PA_BAD_FORMAT;

    string encoded;
    for (int index = 0; index < group.GetCount(); index++)
    {
        string item;
        item.Format("%d", colors[index]);
        if (index)
            encoded += " ";
        encoded += item;
    }
    if (!LT_set_var("__PAT1X09GROUPCOUNT", group.GetCount())
        || !LT_set_str("__PAT1X09GROUPCOLORS$", encoded))
        return PA_BAD_FORMAT;
    return PA_OK;
}

int plotagent_set_x40_group_style(
    string graph_name,
    int layer_index,
    int shape_1,
    int shape_2,
    double size_1,
    double size_2,
    int interior_1,
    int interior_2,
    int edge_color_1,
    int edge_color_2,
    int fill_color_1,
    int fill_color_2,
    int connector_visible,
    int connector_style,
    double connector_width,
    int connector_color
)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    GroupPlot group = layer.Groups(0);
    if (!group || group.GetCount() != 2)
        return PA_MISSING_NODE;

    /*
       Before/After is one dependent PID-206 group.  Ungrouping it destroys
       the row-wise Connect Data Points relationship, so member styles must be
       expressed through the group's native increment lists.
    */
    vector<int> nester(3);
    nester[0] = 3;  /* symbol shape */
    nester[1] = 4;  /* symbol size */
    nester[2] = 8;  /* symbol interior */
    group.Increment.Nested.nVal = 0;
    group.Increment.Nester.nVals = nester;

    vector<int> shapes(2), interiors(2), edge_colors(2), fill_colors(2);
    shapes[0] = shape_1;
    shapes[1] = shape_2;
    interiors[0] = interior_1;
    interiors[1] = interior_2;
    edge_colors[0] = edge_color_1;
    edge_colors[1] = edge_color_2;
    fill_colors[0] = fill_color_1;
    fill_colors[1] = fill_color_2;
    string symbol_sizes;
    symbol_sizes.Format("%.12g %.12g", size_1, size_2);

    Tree format;
    format.Root.Increment.Shape.nVals = shapes;
    format.Root.Increment.SymbolSize.strVal = symbol_sizes;
    format.Root.Increment.SymbolInterior.nVals = interiors;
    format.Root.Increment.EdgeColor.nVals = edge_colors;
    format.Root.Increment.FillColor.nVals = fill_colors;
    format.Root.BoxChart.ConnectLine.ShowDataLine.nVal = connector_visible;
    format.Root.BoxChart.ConnectLine.DataPointsStyle.nVal = connector_style;
    format.Root.BoxChart.ConnectLine.DataPointsWidth.dVal = connector_width;
    format.Root.BoxChart.ConnectLine.DataPointsColor.nVal = connector_color;
    format.Root.BoxChart.ConnectLine.ConnectbySubgroup.nVal = 1;
    if (group.UpdateThemeIDs(format.Root) != 0)
        return PA_BAD_FORMAT;
    return group.ApplyFormat(format, true, true) ? PA_OK : PA_APPLY_FAILED;
}

int plotagent_read_x40_group_style(string graph_name, int layer_index)
{
    GraphPage page(graph_name);
    if (!page)
        return PA_BAD_PAGE;
    GraphLayer layer = page.Layers(layer_index - 1);
    if (!layer)
        return PA_BAD_LAYER;
    GroupPlot group = layer.Groups(0);
    if (!group || group.GetCount() != 2)
        return PA_MISSING_NODE;
    Tree format;
    format = group.GetFormat(FPB_ALL, FOB_ALL, true, true);
    if (!format || !format.Root.Increment || !format.Root.Symbol
        || !format.Root.BoxChart || !format.Root.BoxChart.ConnectLine)
        return PA_BAD_FORMAT;

    vector<int> stretch, shapes, interiors, edge_colors, fill_colors;
    stretch = format.Root.Increment.Stretch.nVals;
    shapes = format.Root.Increment.Shape.nVals;
    interiors = format.Root.Increment.SymbolInterior.nVals;
    edge_colors = format.Root.Increment.EdgeColor.nVals;
    fill_colors = format.Root.Increment.FillColor.nVals;
    if (stretch.GetSize() <= 8 || shapes.GetSize() < 2 || interiors.GetSize() < 2
        || edge_colors.GetSize() < 2 || fill_colors.GetSize() < 2)
        return PA_BAD_FORMAT;

    TreeNode connector = format.Root.BoxChart.ConnectLine;
    if (!LT_set_var("__PAT1X40GROUPCOUNT", group.GetCount())
        || !LT_set_var(
            "__PAT1X40SUBGROUPSIZE",
            format.Root.Subgrouping.SubgroupSize.nVal
        )
        || !LT_set_var("__PAT1X40STRETCHCOLOR", stretch[0])
        || !LT_set_var("__PAT1X40STRETCHSHAPE", stretch[3])
        || !LT_set_var("__PAT1X40STRETCHSIZE", stretch[4])
        || !LT_set_var("__PAT1X40STRETCHINTERIOR", stretch[8])
        || !LT_set_var("__PAT1X40BASESHAPE", format.Root.Symbol.Shape.nVal)
        || !LT_set_var("__PAT1X40BASESIZE", format.Root.Symbol.Size.dVal)
        || !LT_set_var("__PAT1X40BASEINTERIOR", format.Root.Symbol.Interior.nVal)
        || !LT_set_var("__PAT1X40BASEEDGE", format.Root.Symbol.EdgeColor.nVal)
        || !LT_set_var("__PAT1X40BASEFILL", format.Root.Symbol.FillColor.nVal)
        || !LT_set_var("__PAT1X40SHAPE1", shapes[0])
        || !LT_set_var("__PAT1X40SHAPE2", shapes[1])
        || !LT_set_var("__PAT1X40INTERIOR1", interiors[0])
        || !LT_set_var("__PAT1X40INTERIOR2", interiors[1])
        || !LT_set_var("__PAT1X40EDGE1", edge_colors[0])
        || !LT_set_var("__PAT1X40EDGE2", edge_colors[1])
        || !LT_set_var("__PAT1X40FILL1", fill_colors[0])
        || !LT_set_var("__PAT1X40FILL2", fill_colors[1])
        || !LT_set_str(
            "__PAT1X40SIZES$",
            format.Root.Increment.SymbolSize.strVal
        )
        || !LT_set_var("__PAT1X40CONNECTSHOW", connector.ShowDataLine.nVal)
        || !LT_set_var("__PAT1X40CONNECTSTYLE", connector.DataPointsStyle.nVal)
        || !LT_set_var("__PAT1X40CONNECTWIDTH", connector.DataPointsWidth.dVal)
        || !LT_set_var("__PAT1X40CONNECTCOLOR", connector.DataPointsColor.nVal)
        || !LT_set_var("__PAT1X40CONNECTSUBGROUP", connector.ConnectbySubgroup.nVal))
        return PA_BAD_FORMAT;
    return PA_OK;
}
