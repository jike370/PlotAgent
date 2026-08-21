/* Reviewed Origin 2024 bridge for shared T1 visual properties. */

#include <Origin.h>

#pragma labtalk(2)

#define PA_OK 0
#define PA_BAD_PAGE -1
#define PA_BAD_LAYER -2
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
    const int gap = 120;
    scale.Attach = ATTACH_TO_PAGE;
    int width = scale.Width;
    int height = scale.Height;
    if ((anchor_code == 0 && width > height)
        || (anchor_code == 1 && height > width))
    {
        int swap = width;
        width = height;
        height = swap;
    }
    scale.Left = left;
    scale.Top = top;
    scale.Width = width;
    scale.Height = height;
    if (anchor_code == 0)
    {
        scale.Left = right + gap;
        scale.Top = top + (bottom - top - height) / 2;
    }
    else
    {
        scale.Left = left + (right - left - width) / 2;
        scale.Top = bottom + gap;
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
        numeric.nVal = LABELS_NUM_DEC;
        custom.strVal = "";
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
