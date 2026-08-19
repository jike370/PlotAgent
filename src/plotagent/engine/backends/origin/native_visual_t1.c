/* Reviewed Origin 2024 bridge for shared T1 visual properties. */

#include <Origin.h>

#pragma labtalk(2)

#define PA_OK 0
#define PA_BAD_PAGE -1
#define PA_BAD_LAYER -2
#define PA_BAD_FORMAT -4
#define PA_MISSING_NODE -5
#define PA_APPLY_FAILED -6

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
