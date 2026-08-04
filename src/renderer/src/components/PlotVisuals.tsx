import type { ChartType } from '../data/chartCatalog'

interface ChartPreviewProps {
  chart: ChartType
  label?: string
}

const axes = (
  <g className="plot-axes">
    <path d="M28 14V105H204" />
    <path d="M28 82H204M28 58H204M28 34H204" className="plot-grid" />
  </g>
)

const linePlot = (
  <>
    {axes}
    <path className="plot-line plot-line--blue" d="M29 91 C48 85 60 69 76 72 S104 51 123 56 S151 33 170 39 S188 24 202 27" />
    <path className="plot-line plot-line--amber" d="M29 95 C48 91 63 84 78 80 S109 75 124 66 S153 62 171 53 S189 50 202 43" />
    <g className="plot-points plot-points--blue">
      <circle cx="29" cy="91" r="2.6" /><circle cx="76" cy="72" r="2.6" /><circle cx="123" cy="56" r="2.6" /><circle cx="170" cy="39" r="2.6" /><circle cx="202" cy="27" r="2.6" />
    </g>
  </>
)

const distributionPlot = (
  <>
    {axes}
    <g className="plot-bars">
      {[88, 76, 59, 37, 28, 40, 63, 81].map((y, index) => <rect key={y} x={38 + index * 19} y={y} width="13" height={105 - y} />)}
    </g>
    <path className="plot-line plot-line--blue" d="M37 98 C58 97 64 64 88 56 S111 20 132 34 S154 68 185 93" />
  </>
)

const boxPlot = (
  <>
    {axes}
    {[54, 99, 144].map((x, index) => (
      <g className={`box-group box-group--${index + 1}`} key={x}>
        <path d={`M${x + 12} ${25 + index * 6}V92M${x + 5} ${25 + index * 6}H${x + 19}M${x + 5} 92H${x + 19}`} />
        <rect x={x} y={43 + index * 5} width="24" height="32" />
        <path d={`M${x} ${59 + index * 4}H${x + 24}`} />
      </g>
    ))}
  </>
)

const barPlot = (
  <>
    {axes}
    <g className="plot-columns">
      <rect x="43" y="59" width="22" height="46" /><rect x="69" y="45" width="22" height="60" />
      <rect x="106" y="38" width="22" height="67" /><rect x="132" y="51" width="22" height="54" />
      <rect x="169" y="24" width="22" height="81" />
    </g>
  </>
)

const heatmapPlot = (
  <>
    <g className="heatmap-grid">
      {Array.from({ length: 7 }, (_, row) => Array.from({ length: 11 }, (_, col) => (
        <rect key={`${row}-${col}`} x={29 + col * 15.5} y={14 + row * 13} width="14.5" height="12" style={{ opacity: 0.18 + (((row * 5 + col * 3) % 8) / 10) }} />
      )))}
    </g>
    <path className="heatmap-tree" d="M29 109H55V116H88V109H118V119H151V109H199" />
  </>
)

const contourPlot = (
  <>
    <rect className="field-bg" x="28" y="14" width="176" height="91" />
    <g className="contours">
      <path d="M38 92C52 69 55 30 85 28C112 25 102 75 130 77C159 80 163 41 195 27" />
      <path d="M34 71C54 52 60 17 88 19C117 22 112 62 136 65C166 69 173 31 199 19" />
      <path d="M33 102C62 86 71 43 91 45C116 48 118 89 141 91C167 94 181 58 202 54" />
    </g>
  </>
)

const survivalPlot = (
  <>
    {axes}
    <path className="plot-line plot-line--blue" d="M29 22H58V34H86V46H112V59H146V75H177V88H202" />
    <path className="plot-line plot-line--amber" d="M29 22H51V29H73V40H99V48H126V62H155V71H184V82H202" />
    <g className="censor-marks"><path d="M83 42v8m-4-4h8M142 71v8m-4-4h8M151 58v8m-4-4h8" /></g>
  </>
)

const dosePlot = (
  <>
    {axes}
    <path className="plot-line plot-line--blue" d="M30 26C78 26 88 31 102 47C116 65 122 91 201 94" />
    <g className="plot-points plot-points--blue">
      <circle cx="40" cy="27" r="3" /><circle cx="72" cy="28" r="3" /><circle cx="99" cy="45" r="3" /><circle cx="120" cy="75" r="3" /><circle cx="151" cy="91" r="3" /><circle cx="190" cy="95" r="3" />
    </g>
  </>
)

const forestPlot = (
  <>
    <path className="forest-zero" d="M125 14V107" />
    {[27, 45, 63, 81, 99].map((y, index) => (
      <g className="forest-row" key={y}>
        <path d={`M${68 + index * 8} ${y}H${167 - index * 6}`} />
        <circle cx={104 + index * 8} cy={y} r={index === 4 ? 5 : 3.2} />
        <path d={`M${68 + index * 8} ${y - 4}V${y + 4}M${167 - index * 6} ${y - 4}V${y + 4}`} />
      </g>
    ))}
  </>
)

const spectrumPlot = (sharp = false) => (
  <>
    {axes}
    <path className="plot-line plot-line--blue" d={sharp ? 'M29 96L39 94L44 88L48 34L53 91L73 96L88 92L94 47L99 94L117 96L129 91L135 25L139 93L156 96L171 90L177 55L182 94L202 96' : 'M29 95C43 94 48 90 54 53C59 89 64 92 77 94C88 93 92 88 97 42C103 88 109 93 121 94C136 93 141 89 145 62C151 90 160 92 174 94C187 94 194 93 202 91'} />
  </>
)

const nyquistPlot = (
  <>
    {axes}
    <path className="plot-line plot-line--blue" d="M37 99C55 62 78 39 103 41C128 43 136 74 153 91C164 102 179 101 201 96" />
    <g className="plot-points plot-points--blue">
      {[['42','90'],['59','64'],['82','45'],['108','44'],['130','67'],['153','91'],['181','99']].map(([cx,cy]) => <circle key={cx} cx={cx} cy={cy} r="2.7" />)}
    </g>
  </>
)

const mapPlot = (
  <>
    <rect className="map-water" x="28" y="14" width="176" height="91" />
    <g className="map-regions">
      <path d="M37 30L72 18L94 34L87 55L53 59Z" /><path d="M96 35L130 19L151 38L132 59L88 55Z" />
      <path d="M53 60L88 56L105 80L83 102L43 88Z" /><path d="M89 57L132 60L145 90L107 102L104 80Z" />
      <path d="M151 39L194 29L199 69L176 94L145 89L132 59Z" />
    </g>
    <path className="map-scale" d="M40 96H79M40 93V99M79 93V99" />
  </>
)

const imagePlot = (
  <>
    <rect className="image-field" x="28" y="14" width="176" height="91" />
    <g className="image-cells">
      {[[48,34,10],[81,52,14],[117,30,9],[152,62,16],[183,35,11],[58,83,13],[111,83,10],[183,84,8]].map(([cx,cy,r]) => <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r={r} />)}
    </g>
    <path className="image-scale" d="M158 95H191" />
  </>
)

export function ChartPreview({ chart, label }: ChartPreviewProps): React.JSX.Element {
  let graphic = linePlot

  if (['histogram', 'density', 'ecdf'].includes(chart.family)) graphic = distributionPlot
  if (['box', 'violin', 'strip'].includes(chart.family)) graphic = boxPlot
  if (['bar', 'grouped-bar', 'stacked-bar'].includes(chart.family)) graphic = barPlot
  if (['heatmap', 'correlation'].includes(chart.family)) graphic = heatmapPlot
  if (chart.family === 'contour') graphic = contourPlot
  if (chart.family === 'survival') graphic = survivalPlot
  if (chart.family === 'dose-response') graphic = dosePlot
  if (chart.family === 'forest') graphic = forestPlot
  if (chart.family === 'spectrum') graphic = spectrumPlot()
  if (chart.family === 'xrd') graphic = spectrumPlot(true)
  if (chart.family === 'nyquist') graphic = nyquistPlot
  if (chart.family === 'map') graphic = mapPlot
  if (chart.family === 'image') graphic = imagePlot
  if (chart.family === 'multi-panel' || chart.family === 'facet') {
    graphic = <><g transform="translate(0 0) scale(.48 .9)">{linePlot}</g><g transform="translate(113 0) scale(.48 .9)">{barPlot}</g></>
  }

  return (
    <svg className="chart-preview" viewBox="0 0 220 120" role="img" aria-label={label ?? `${chart.name}缩略图`}>
      <rect className="plot-paper" width="220" height="120" rx="3" />
      {graphic}
    </svg>
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
