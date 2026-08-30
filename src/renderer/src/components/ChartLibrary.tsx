import { useMemo, useState } from 'react'
import {
  Bookmark,
  Check,
  ChevronLeft,
  CircleAlert,
  Clock3,
  Combine,
  Download,
  Filter,
  FolderTree,
  Grid2X2,
  Layers3,
  Library,
  Search,
  Star,
  X,
} from 'lucide-react'

import {
  chartCatalog,
  chartCategories,
  filterCharts,
  type ChartFilters,
  type ChartType,
} from '../data/chartCatalog'
import { chartCompatibility } from '../data/chartCompatibility'
import { ChartPreview } from './PlotVisuals'
import { useDialogFocus } from './useDialogFocus'

interface ChartLibraryProps {
  currentChartId?: string
  datasetCompatibility?: {
    numericFieldCount: number
    categoricalFieldCount: number
    datetimeFieldCount?: number
    totalFieldCount: number
  }
  onClose: () => void
  onSelect: (chart: ChartType) => void
}

const initialFilters: ChartFilters = {
  query: '',
  layer: 'all',
  category: '全部',
  capability: 'all',
  collection: 'all',
}

const batchLabels = {
  direct: '直接批量',
  conditional: '条件批量',
  manual: '人工布局',
}

const layoutLabels = {
  layer: '同层组合',
  panel: '面板组合',
}

const coreChartCount = chartCatalog.filter((chart) => chart.layer === 'core').length
const validationChartCount = chartCatalog.filter((chart) => chart.layer === 'validation').length

export function ChartLibrary({ currentChartId, datasetCompatibility, onClose, onSelect }: ChartLibraryProps): React.JSX.Element {
  const dialogRef = useDialogFocus<HTMLDivElement>()
  const [filters, setFilters] = useState(initialFilters)
  const [selectedId, setSelectedId] = useState(currentChartId ?? 'K02')
  const filteredCharts = useMemo(() => filterCharts(chartCatalog, filters), [filters])
  const selectedChart = filteredCharts.find((item) => item.id === selectedId) ?? filteredCharts[0]
  const compatibility = selectedChart
    ? chartCompatibility(selectedChart, datasetCompatibility)
    : { compatible: false }

  const updateFilter = <Key extends keyof ChartFilters>(key: Key, value: ChartFilters[Key]): void => {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  return (
    <div ref={dialogRef} className="library-layer" role="dialog" aria-modal="true" aria-labelledby="library-title" tabIndex={-1}>
      <header className="library-header">
        <button className="back-button" type="button" onClick={onClose}><ChevronLeft size={18} />返回对话</button>
        <h2 id="library-title">图形库</h2>
        <label className="library-search">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">搜索图形库</span>
          <input
            data-autofocus
            aria-label="搜索图形库"
            value={filters.query}
            onChange={(event) => updateFilter('query', event.target.value)}
            placeholder="搜索名称、缩写、学科、数据形状或稳定 ID"
          />
          {filters.query && <button type="button" onClick={() => updateFilter('query', '')} aria-label="清除搜索"><X size={15} /></button>}
          <kbd>Ctrl K</kbd>
        </label>
        <button className="icon-button" type="button" onClick={onClose} aria-label="关闭图形库"><X size={19} /></button>
      </header>

      <div className="library-body">
        <aside className="library-sidebar" aria-label="图形库分类">
          <div className="library-nav-group">
            <span className="section-label">集合</span>
            <button className={filters.collection === 'all' ? 'is-active' : ''} type="button" onClick={() => updateFilter('collection', 'all')}><Library size={15} />全部图形<span>{chartCatalog.length}</span></button>
            <button className={filters.collection === 'recent' ? 'is-active' : ''} type="button" onClick={() => updateFilter('collection', 'recent')}><Clock3 size={15} />最近使用</button>
            <button className={filters.collection === 'favorites' ? 'is-active' : ''} type="button" onClick={() => updateFilter('collection', 'favorites')}><Star size={15} />收藏</button>
          </div>
          <div className="library-nav-group">
            <span className="section-label">产品分层</span>
            <button className={filters.layer === 'all' ? 'is-active' : ''} type="button" onClick={() => updateFilter('layer', 'all')}><Grid2X2 size={15} />全部层级</button>
            <button className={filters.layer === 'core' ? 'is-active' : ''} type="button" onClick={() => updateFilter('layer', 'core')}><Layers3 size={15} />核心数值图表<span>{coreChartCount}</span></button>
            <button className={filters.layer === 'validation' ? 'is-active' : ''} type="button" onClick={() => updateFilter('layer', 'validation')}><Bookmark size={15} />跨学科验证<span>{validationChartCount}</span></button>
          </div>
          <div className="library-nav-group library-category-tree">
            <span className="section-label">用途与领域</span>
            {chartCategories.map((category) => (
              <button className={filters.category === category ? 'is-active' : ''} key={category} type="button" onClick={() => updateFilter('category', category)}>
                {category === '全部' ? <FolderTree size={15} /> : <span className="tree-node" />}
                {category}
              </button>
            ))}
          </div>
        </aside>

        <section className="library-results" aria-label="图形搜索结果">
          <div className="results-toolbar">
            <div>
              <strong>{filteredCharts.length} 个图形</strong>
            </div>
            <div className="filter-pills" aria-label="能力筛选">
              <Filter size={15} />
              {[
                ['all', '全部能力'],
                ['batch', '支持批量'],
                ['layout', '多面板布局'],
                ['opju', '原生/组合 OPJU'],
              ].map(([value, label]) => (
                <button className={filters.capability === value ? 'is-active' : ''} key={value} type="button" onClick={() => updateFilter('capability', value as ChartFilters['capability'])}>{label}</button>
              ))}
            </div>
          </div>

          {filteredCharts.length > 0 ? (
            <div className="chart-grid">
              {filteredCharts.map((chart) => (
                <button
                  className={`chart-card${selectedChart?.id === chart.id ? ' is-selected' : ''}`}
                  type="button"
                  key={chart.id}
                  onClick={() => setSelectedId(chart.id)}
                  aria-label={`${chart.id} ${chart.name}`}
                  aria-current={selectedChart?.id === chart.id ? 'true' : undefined}
                >
                  <div className="chart-card__preview"><ChartPreview chart={chart} /></div>
                  <div className="chart-card__heading">
                    <span className={`chart-id chart-id--${chart.layer}`}>{chart.id}</span>
                    <strong>{chart.name}</strong>
                    {chart.favorite && <Star className="favorite-star" size={15} fill="currentColor" aria-label="已收藏" />}
                  </div>
                  {chart.id === currentChartId && <span className="current-chart"><Check size={12} />当前</span>}
                </button>
              ))}
            </div>
          ) : (
            <div className="no-results">
              <Search size={24} />
              <strong>没有匹配项</strong>
              <p>尝试中文名、英文缩写、稳定 ID 或放宽能力筛选。</p>
              <button type="button" onClick={() => setFilters(initialFilters)}>清除筛选</button>
            </div>
          )}
        </section>

        {selectedChart && (
          <aside className="chart-detail" aria-label={`${selectedChart.name}详情`}>
            <div className="chart-detail__preview"><ChartPreview chart={selectedChart} label={`${selectedChart.name}示例`} /></div>
            <div className="chart-detail__title">
              <span className={`chart-id chart-id--${selectedChart.layer}`}>{selectedChart.id}</span>
              <div><h3>{selectedChart.name}</h3><p>{selectedChart.englishName}</p></div>
              <button type="button" aria-label={selectedChart.favorite ? '取消收藏' : '收藏图形'}><Star size={17} fill={selectedChart.favorite ? 'currentColor' : 'none'} /></button>
            </div>
            <p className="chart-detail__purpose">{selectedChart.purpose}</p>
            <dl className="detail-list">
              <div><dt>所需字段</dt><dd>{selectedChart.requiredFields.join(' · ')}</dd></div>
              <div><dt>数据形状</dt><dd>{selectedChart.dataShape.join(' / ')}</dd></div>
              <div><dt>典型学科</dt><dd>{selectedChart.domains.join(' · ')}</dd></div>
              <div><dt>核心参数</dt><dd>{selectedChart.optionalParameters.join(' · ')}</dd></div>
              <div><dt>批量模式</dt><dd>{batchLabels[selectedChart.batchMode]}</dd></div>
              <div><dt>布局结构</dt><dd>{layoutLabels[selectedChart.layoutMode]}</dd></div>
            </dl>

            <div className="export-contract">
              <strong>导出能力</strong>
              <div>
                <span><Download size={14} />PNG</span>
                <span><Combine size={14} />SVG 矢量</span>
                <span><Layers3 size={14} />OPJU {selectedChart.export.opju}</span>
              </div>
            </div>

            <div className={`compatibility-check${compatibility.compatible ? '' : ' is-incompatible'}`}>
              {compatibility.compatible ? <Check size={16} /> : <CircleAlert size={16} />}
              <strong>{compatibility.awaitingData ? '可先选择图形' : compatibility.compatible ? '当前数据可进入映射' : '当前数据尚不兼容'}</strong>
            </div>

            <button className="select-chart-button" type="button" disabled={!compatibility.compatible} onClick={() => onSelect(selectedChart)}>选择此图形</button>
          </aside>
        )}
      </div>
    </div>
  )
}
