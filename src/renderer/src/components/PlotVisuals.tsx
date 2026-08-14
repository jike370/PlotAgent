import type { ChartType } from '../data/chartCatalog'
import { chartPreviewSource } from '../data/chartPreviewAssets'

interface ChartPreviewProps {
  chart: ChartType
  label?: string
}

export function ChartPreview({ chart, label }: ChartPreviewProps): React.JSX.Element {
  return (
    <img
      className="chart-preview"
      src={chartPreviewSource(chart.id)}
      alt={label ?? `${chart.name}缩略图`}
      loading="lazy"
    />
  )
}

interface BatchPlotProps {
  title: string
  series?: 'control' | 'treated' | 'recovery'
  compact?: boolean
}

export function BatchPlot({ title, series = 'control', compact = false }: BatchPlotProps): React.JSX.Element {
  const paths = {
    control: ['M42 115C70 110 84 91 107 93S145 61 172 70S216 37 270 43', 'M42 119C83 115 97 106 124 102S164 87 196 78S235 71 270 62'],
    treated: ['M42 112C66 104 90 78 109 84S146 47 173 57S214 29 270 36', 'M42 119C74 114 92 100 122 96S161 73 193 76S231 59 270 50'],
    recovery: ['M42 116C74 111 91 94 113 97S148 68 177 74S216 45 270 49', 'M42 120C83 117 104 106 128 103S170 91 199 84S239 76 270 70'],
  }

  return (
    <svg className={`batch-plot${compact ? ' batch-plot--compact' : ''}`} viewBox="0 0 310 160" role="img" aria-label={`${title}线点图`}>
      <rect className="plot-paper" width="310" height="160" />
      <g className="plot-axes">
        <path d="M41 19V127H283" />
        <path className="plot-grid" d="M41 100H283M41 73H283M41 46H283" />
      </g>
      <path className="plot-ribbon" d={`${paths[series][0]}L270 50C218 42 211 52 172 79S128 105 107 102S72 120 42 124Z`} />
      <path className="plot-line plot-line--blue" d={paths[series][0]} />
      <path className="plot-line plot-line--amber" d={paths[series][1]} />
      <g className="plot-points plot-points--blue">
        <circle cx="42" cy="115" r="3" /><circle cx="107" cy="93" r="3" /><circle cx="172" cy="70" r="3" /><circle cx="270" cy="43" r="3" />
      </g>
      {!compact && <>
        <text className="plot-title" x="41" y="14">{title}</text>
        <text className="plot-label" x="142" y="151">Time (min)</text>
        <text className="plot-label" transform="translate(12 102) rotate(-90)">Fluorescence (a.u.)</text>
      </>}
    </svg>
  )
}
