import { useState } from 'react'
import {
  AlignCenter,
  ArrowLeft,
  Check,
  ChevronDown,
  Columns2,
  Download,
  FileImage,
  Grid2X2,
  Image as ImageIcon,
  Layers3,
  Link2,
  Lock,
  MoreHorizontal,
  Plus,
  RectangleHorizontal,
  Rows2,
  Settings2,
  Type,
  X,
} from 'lucide-react'

import { chartCatalog } from '../data/chartCatalog'
import { ChartPreview } from './PlotVisuals'

type Layout = '1x2' | '2x1' | '2x2'

interface CompositionEditorProps {
  onClose: () => void
}

export function CompositionEditor({ onClose }: CompositionEditorProps): React.JSX.Element {
  const [layout, setLayout] = useState<Layout>('1x2')
  const [commonLegend, setCommonLegend] = useState(true)
  const [labels, setLabels] = useState(true)
  const [selectedPanel, setSelectedPanel] = useState('A')
  const line = chartCatalog.find((chart) => chart.id === 'K02')!
  const bar = chartCatalog.find((chart) => chart.id === 'K09')!
  const image = chartCatalog.find((chart) => chart.id === 'K23')!
  const heatmap = chartCatalog.find((chart) => chart.id === 'K20')!

  const panels = layout === '1x2'
    ? [{ id: 'A', chart: line, source: 'Sample A · v3' }, { id: 'B', chart: image, source: 'Microscopy · image-01' }]
    : layout === '2x1'
      ? [{ id: 'A', chart: line, source: 'Sample A · v3' }, { id: 'B', chart: bar, source: 'Group summary · v2' }]
      : [
          { id: 'A', chart: line, source: 'Sample A · v3' },
          { id: 'B', chart: bar, source: 'Group summary · v2' },
          { id: 'C', chart: image, source: 'Microscopy · image-01' },
          { id: 'D', chart: heatmap, source: 'Correlation · v1' },
        ]

  return (
    <div className="composition-editor" role="dialog" aria-modal="true" aria-label="组合图编辑">
      <header className="focus-header composition-header">
        <button className="back-button" type="button" onClick={onClose}><ArrowLeft size={18} />返回对话</button>
        <div className="focus-title"><h2>组合图 · Figure 1</h2><span>固定布局 · 自动保存</span></div>
        <div className="composition-header-tools">
          <button type="button"><Link2 size={16} />源版本</button>
          <button type="button"><Settings2 size={16} />发表规格</button>
          <button className="primary-button" type="button"><Download size={16} />导出组合图<ChevronDown size={14} /></button>
          <button className="icon-button" type="button" onClick={onClose} aria-label="关闭组合图编辑"><X size={19} /></button>
        </div>
      </header>

      <div className="composition-body">
        <aside className="composition-controls" aria-label="组合图设置">
          <section>
            <h3>固定布局</h3>
            <div className="layout-options">
              <button className={layout === '1x2' ? 'is-active' : ''} type="button" onClick={() => setLayout('1x2')}><Columns2 size={18} /><span>1 × 2</span></button>
              <button className={layout === '2x1' ? 'is-active' : ''} type="button" onClick={() => setLayout('2x1')}><Rows2 size={18} /><span>2 × 1</span></button>
              <button className={layout === '2x2' ? 'is-active' : ''} type="button" onClick={() => setLayout('2x2')}><Grid2X2 size={18} /><span>2 × 2</span></button>
            </div>
          </section>
          <section>
            <h3>面板规则</h3>
            <label className="switch-row"><span><Type size={15} />面板编号 A/B/C/D</span><input type="checkbox" checked={labels} onChange={(event) => setLabels(event.target.checked)} /></label>
            <label className="switch-row"><span><Layers3 size={15} />使用公共图例</span><input type="checkbox" checked={commonLegend} onChange={(event) => setCommonLegend(event.target.checked)} /></label>
            <button className="control-row" type="button"><AlignCenter size={15} />统一面板间距<span>4 mm</span></button>
            <button className="control-row" type="button"><RectangleHorizontal size={15} />页面边距<span>6 mm</span></button>
          </section>
          <section>
            <h3>当前面板 {selectedPanel}</h3>
            <div className="selected-panel-info">
              <span className="panel-letter">{selectedPanel}</span>
              <div><strong>{panels.find((panel) => panel.id === selectedPanel)?.chart.name}</strong><p>{panels.find((panel) => panel.id === selectedPanel)?.source}</p></div>
            </div>
            <button className="wide-secondary" type="button">替换面板内容</button>
          </section>
          <div className="source-contract">
            <Lock size={15} />
            <p>组合图引用指定源版本。布局修改不会反向改变源图。</p>
          </div>
        </aside>

        <main className="composition-stage">
          <div className="composition-stage-toolbar">
            <span>Nature · 双栏 · 183 × 88 mm</span>
            <div><button type="button">适合窗口</button><span>92%</span></div>
          </div>
          <div className="figure-page-wrap">
            <div className={`figure-page figure-page--${layout}`}>
              {panels.map((panel) => (
                <button className={`figure-panel${selectedPanel === panel.id ? ' is-selected' : ''}`} type="button" key={panel.id} onClick={() => setSelectedPanel(panel.id)}>
                  {labels && <span className="figure-label">{panel.id}</span>}
                  <ChartPreview chart={panel.chart} label={`面板 ${panel.id} ${panel.chart.name}`} />
                  <span className="panel-source"><Link2 size={11} />{panel.source}</span>
                  <span className="panel-menu" aria-hidden="true"><MoreHorizontal size={15} /></span>
                </button>
              ))}
              {commonLegend && (
                <div className="common-legend" aria-label="公共图例">
                  <span><i className="legend-line legend-line--blue" />Control</span>
                  <span><i className="legend-line legend-line--amber" />Treated</span>
                  <span><i className="legend-dot" />Recovery</span>
                </div>
              )}
            </div>
          </div>
          <div className="composition-validation"><Check size={14} />面板编号、字体与间距符合当前发表规格<span>SVG 中的图像面板将保留为栅格</span></div>
        </main>

        <aside className="asset-tray" aria-label="可用图表与图片">
          <header><div><strong>项目资产</strong><span>温度响应实验</span></div><button type="button" aria-label="项目资产更多操作"><MoreHorizontal size={17} /></button></header>
          <div className="asset-tabs"><button className="is-active" type="button">图表</button><button type="button">图片</button></div>
          <label className="asset-search"><span className="sr-only">搜索项目资产</span><input placeholder="搜索图表或图片" /></label>
          <div className="asset-list">
            {[line, bar, heatmap].map((chart, index) => (
              <button type="button" key={chart.id}>
                <span><ChartPreview chart={chart} /></span>
                <div><strong>{chart.name}</strong><small>{index === 0 ? 'Sample B · v3' : index === 1 ? 'Group summary · v2' : 'Correlation · v1'}</small></div>
                <Plus size={15} />
              </button>
            ))}
            <button type="button">
              <span><ChartPreview chart={image} /></span>
              <div><strong>显微图像</strong><small>image-01.tif · 2048 px</small></div>
              <Plus size={15} />
            </button>
          </div>
          <button className="import-asset" type="button"><ImageIcon size={15} />导入图片面板</button>
          <div className="mixed-export-note"><FileImage size={15} /><p>当前组合包含矢量图与图片面板，PNG 完整支持，SVG 为混合内容。</p></div>
        </aside>
      </div>
    </div>
  )
}
