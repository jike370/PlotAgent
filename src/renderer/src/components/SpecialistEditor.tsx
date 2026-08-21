import { useState } from 'react'

import type { JsonValue } from '../../../shared/desktop-contract'
import type { ProductPlot } from '../data/productState'

interface SpecialistEditorProps {
  capabilities: ReadonlySet<string>
  plot: ProductPlot
  disabled: boolean
  onApply: (operation: string, values: Record<string, JsonValue>) => Promise<void>
}

function commaValues(value: string): string[] {
  return value.split(',').map((item) => item.trim()).filter(Boolean)
}

function labelValues(value: string): { value: string; label: string }[] {
  return value.split(';').flatMap((item) => {
    const [source, ...labelParts] = item.split('=')
    const label = labelParts.join('=').trim()
    return source.trim() && label ? [{ value: source.trim(), label }] : []
  })
}

function safeRichText(value: string): JsonValue {
  return value.trim() === '' ? null : { nodes: [{ kind: 'plain', text: value.trim() }] }
}

export function SpecialistEditor({
  capabilities,
  plot,
  disabled,
  onApply,
}: SpecialistEditorProps): React.JSX.Element {
  const specialist = plot.specialist
  const [fillColor, setFillColor] = useState(specialist.barArea.fillColor ?? '#2A6FDB')
  const [edgeColor, setEdgeColor] = useState(specialist.barArea.edgeColor ?? '#1F2937')
  const [edgeWidth, setEdgeWidth] = useState(specialist.barArea.edgeWidthPt)
  const [widthRatio, setWidthRatio] = useState(specialist.barArea.widthRatio)
  const [barAlpha, setBarAlpha] = useState(specialist.barArea.alpha)
  const [uncertaintyColor, setUncertaintyColor] = useState(
    specialist.uncertainty.color ?? '#1F2937',
  )
  const [uncertaintyWidth, setUncertaintyWidth] = useState(
    specialist.uncertainty.lineWidthPt,
  )
  const [capSize, setCapSize] = useState(specialist.uncertainty.capSizePt)
  const [bandAlpha, setBandAlpha] = useState(specialist.uncertainty.bandAlpha)
  const [colorbarVisible, setColorbarVisible] = useState(specialist.colorbar.visible)
  const [colorbarTitle, setColorbarTitle] = useState(specialist.colorbar.title)
  const [colorbarMinimum, setColorbarMinimum] = useState(
    specialist.colorbar.minimum?.toString() ?? '',
  )
  const [colorbarMaximum, setColorbarMaximum] = useState(
    specialist.colorbar.maximum?.toString() ?? '',
  )
  const [colorbarLevels, setColorbarLevels] = useState(specialist.colorbar.levels)
  const [leftAxisColor, setLeftAxisColor] = useState(
    specialist.dualY.leftColor ?? '#2A6FDB',
  )
  const [rightAxisColor, setRightAxisColor] = useState(
    specialist.dualY.rightColor ?? '#D9485F',
  )
  const [dualAxisWidth, setDualAxisWidth] = useState(specialist.dualY.axisWidthPt)
  const [facetOrder, setFacetOrder] = useState(specialist.facet.order.join(', '))
  const [facetLabels, setFacetLabels] = useState(
    specialist.facet.labels.map((item) => `${item.value}=${item.label}`).join('; '),
  )
  const [facetGap, setFacetGap] = useState(specialist.facet.gapMm)
  const [sharedX, setSharedX] = useState(specialist.facet.sharedX)
  const [sharedY, setSharedY] = useState(specialist.facet.sharedY)
  const [commonLegend, setCommonLegend] = useState(specialist.facet.commonLegend)
  const [offsetDistance, setOffsetDistance] = useState(
    specialist.yOffset.distance?.toString() ?? '',
  )
  const [offsetOrder, setOffsetOrder] = useState(specialist.yOffset.order.join(', '))
  const [paretoReference, setParetoReference] = useState(
    specialist.chartParameters.paretoReferencePercent,
  )
  const hasBar = ['bar_fill', 'bar_edge', 'bar_width', 'bar_gap'].some((item) =>
    capabilities.has(item),
  )
  const hasUncertainty = capabilities.has('error_style') || capabilities.has('band_style')

  return (
    <>
      {hasBar && (
        <form className="parameter-section" onSubmit={(event) => {
          event.preventDefault()
          void onApply('set_bar_area_style', {
            style: {
              fill_color: { value: fillColor },
              edge_color: { value: edgeColor },
              edge_width: { value: edgeWidth, unit: 'pt' },
              width_ratio: widthRatio,
              alpha: barAlpha,
            },
          })
        }}>
          <h3>柱与面积</h3>
          <label><span>填充色</span><input aria-label="柱与面积填充色" type="color" value={fillColor} onChange={(event) => setFillColor(event.target.value)} /></label>
          <label><span>边框色</span><input aria-label="柱与面积边框色" type="color" value={edgeColor} onChange={(event) => setEdgeColor(event.target.value)} /></label>
          <label><span>边框宽度</span><div className="unit-input"><input aria-label="柱与面积边框宽度" type="number" min="0.1" max="20" step="0.1" value={edgeWidth} onChange={(event) => setEdgeWidth(event.target.valueAsNumber)} /><span>pt</span></div></label>
          <label><span>宽度比例</span><input aria-label="柱宽比例" type="number" min="0.05" max="1" step="0.05" value={widthRatio} onChange={(event) => setWidthRatio(event.target.valueAsNumber)} /></label>
          <label><span>不透明度</span><input aria-label="柱与面积不透明度" type="number" min="0.05" max="1" step="0.05" value={barAlpha} onChange={(event) => setBarAlpha(event.target.valueAsNumber)} /></label>
          <button className="parameter-apply" type="submit" disabled={disabled}>应用柱与面积样式</button>
        </form>
      )}

      {hasUncertainty && (
        <form className="parameter-section" onSubmit={(event) => {
          event.preventDefault()
          void onApply('set_uncertainty_style', {
            style: {
              color: { value: uncertaintyColor },
              line_width: { value: uncertaintyWidth, unit: 'pt' },
              cap_size: { value: capSize, unit: 'pt' },
              band_alpha: bandAlpha,
            },
          })
        }}>
          <h3>误差与置信带</h3>
          <label><span>颜色</span><input aria-label="误差颜色" type="color" value={uncertaintyColor} onChange={(event) => setUncertaintyColor(event.target.value)} /></label>
          <label><span>线宽</span><div className="unit-input"><input aria-label="误差线宽" type="number" min="0.1" max="20" step="0.1" value={uncertaintyWidth} onChange={(event) => setUncertaintyWidth(event.target.valueAsNumber)} /><span>pt</span></div></label>
          <label><span>端帽大小</span><div className="unit-input"><input aria-label="误差端帽大小" type="number" min="0.5" max="72" step="0.5" value={capSize} onChange={(event) => setCapSize(event.target.valueAsNumber)} /><span>pt</span></div></label>
          <label><span>带透明度</span><input aria-label="置信带透明度" type="number" min="0.05" max="1" step="0.05" value={bandAlpha} onChange={(event) => setBandAlpha(event.target.valueAsNumber)} /></label>
          <button className="parameter-apply" type="submit" disabled={disabled}>应用误差样式</button>
        </form>
      )}

      {capabilities.has('colorbar') && (
        <form className="parameter-section" onSubmit={(event) => {
          event.preventDefault()
          void onApply('set_colorbar_style', {
            style: {
              visible: colorbarVisible,
              title: safeRichText(colorbarTitle),
              minimum: colorbarMinimum === '' ? null : Number(colorbarMinimum),
              maximum: colorbarMaximum === '' ? null : Number(colorbarMaximum),
              levels: colorbarLevels,
            },
          })
        }}>
          <h3>色带</h3>
          <label className="parameter-check"><input aria-label="显示色带" type="checkbox" checked={colorbarVisible} onChange={(event) => setColorbarVisible(event.target.checked)} /><span>显示色带</span></label>
          <label><span>标题</span><input aria-label="色带标题" maxLength={256} value={colorbarTitle} onChange={(event) => setColorbarTitle(event.target.value)} /></label>
          <label><span>最小值</span><input aria-label="色带最小值" type="number" placeholder="自动" value={colorbarMinimum} onChange={(event) => setColorbarMinimum(event.target.value)} /></label>
          <label><span>最大值</span><input aria-label="色带最大值" type="number" placeholder="自动" value={colorbarMaximum} onChange={(event) => setColorbarMaximum(event.target.value)} /></label>
          <label><span>色阶数</span><input aria-label="色带色阶数" type="number" min="2" max="64" value={colorbarLevels} onChange={(event) => setColorbarLevels(event.target.valueAsNumber)} /></label>
          <button className="parameter-apply" type="submit" disabled={disabled || (colorbarMinimum === '') !== (colorbarMaximum === '')}>应用色带</button>
        </form>
      )}

      {capabilities.has('dual_y_style') && (
        <form className="parameter-section" onSubmit={(event) => {
          event.preventDefault()
          void onApply('set_dual_y_style', {
            style: {
              left_color: { value: leftAxisColor },
              right_color: { value: rightAxisColor },
              axis_width: { value: dualAxisWidth, unit: 'pt' },
            },
          })
        }}>
          <h3>双 Y 轴</h3>
          <label><span>左轴颜色</span><input aria-label="左 Y 轴颜色" type="color" value={leftAxisColor} onChange={(event) => setLeftAxisColor(event.target.value)} /></label>
          <label><span>右轴颜色</span><input aria-label="右 Y 轴颜色" type="color" value={rightAxisColor} onChange={(event) => setRightAxisColor(event.target.value)} /></label>
          <label><span>轴线宽度</span><div className="unit-input"><input aria-label="双 Y 轴线宽" type="number" min="0.1" max="20" step="0.1" value={dualAxisWidth} onChange={(event) => setDualAxisWidth(event.target.valueAsNumber)} /><span>pt</span></div></label>
          <button className="parameter-apply" type="submit" disabled={disabled}>应用双 Y 轴样式</button>
        </form>
      )}

      {capabilities.has('panel_style') && (
        <form className="parameter-section" onSubmit={(event) => {
          event.preventDefault()
          void onApply('set_facet_style', {
            style: {
              order: commaValues(facetOrder),
              labels: labelValues(facetLabels),
              gap: { value: facetGap, unit: 'mm' },
              shared_x: sharedX,
              shared_y: sharedY,
              common_legend: commonLegend,
            },
          })
        }}>
          <h3>分面</h3>
          <label><span>顺序</span><input aria-label="分面顺序" value={facetOrder} placeholder="A, B, C" onChange={(event) => setFacetOrder(event.target.value)} /></label>
          <label><span>标签替换</span><input aria-label="分面标签替换" value={facetLabels} placeholder="A=处理组; B=对照组" onChange={(event) => setFacetLabels(event.target.value)} /></label>
          <label><span>面板间距</span><div className="unit-input"><input aria-label="分面间距" type="number" min="0.1" max="20" step="0.5" value={facetGap} onChange={(event) => setFacetGap(event.target.valueAsNumber)} /><span>mm</span></div></label>
          <label className="parameter-check"><input type="checkbox" checked={sharedX} onChange={(event) => setSharedX(event.target.checked)} /><span>共享 X 范围</span></label>
          <label className="parameter-check"><input type="checkbox" checked={sharedY} onChange={(event) => setSharedY(event.target.checked)} /><span>共享 Y 范围</span></label>
          <label className="parameter-check"><input type="checkbox" checked={commonLegend} onChange={(event) => setCommonLegend(event.target.checked)} /><span>共用图例</span></label>
          <button className="parameter-apply" type="submit" disabled={disabled}>应用分面设置</button>
        </form>
      )}

      {capabilities.has('y_offset') && (
        <form className="parameter-section" onSubmit={(event) => {
          event.preventDefault()
          void onApply('set_y_offset_style', {
            style: {
              distance: offsetDistance === '' ? null : Number(offsetDistance),
              order: commaValues(offsetOrder),
            },
          })
        }}>
          <h3>Y 偏移</h3>
          <label><span>偏移距离</span><input aria-label="Y 偏移距离" type="number" min="0" step="any" placeholder="自动" value={offsetDistance} onChange={(event) => setOffsetDistance(event.target.value)} /></label>
          <label><span>系列顺序</span><input aria-label="Y 偏移系列顺序" value={offsetOrder} placeholder="系列 A, 系列 B" onChange={(event) => setOffsetOrder(event.target.value)} /></label>
          <p className="parameter-note">偏移只影响显示，不修改源数据。</p>
          <button className="parameter-apply" type="submit" disabled={disabled || (offsetDistance !== '' && Number(offsetDistance) <= 0)}>应用 Y 偏移</button>
        </form>
      )}

      {capabilities.has('chart_parameters') && (
        <form className="parameter-section" onSubmit={(event) => {
          event.preventDefault()
          void onApply('set_chart_parameters', {
            parameters: {
              pareto_reference_percent: paretoReference,
            },
          })
        }}>
          <h3>图型固定参数</h3>
          {plot.chartId === 'X24' && <label><span>累计参考线</span><div className="unit-input"><input aria-label="帕累托参考百分比" type="number" min="0" max="100" step="1" value={paretoReference} onChange={(event) => setParetoReference(event.target.valueAsNumber)} /><span>%</span></div></label>}
          <button className="parameter-apply" type="submit" disabled={disabled}>应用图型参数</button>
        </form>
      )}
    </>
  )
}
