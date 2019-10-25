/*******************************************************************************
D3 based widgets (http://d3js.com)

This file defines and exports two basic widgets:
  - TimelineWidget
  - DialWidget (not implemented yet)
********************************************************************************/

/**********************
// TimelineWidget definition

Create a D3 line widget displaying one or more variables

  container - name of div on page to use for displaying widget

  fields - associative array of fieldName:{options} for widget

  yLabel - label to use for widget's y-axis

  widgetOptions - an optional associative array of options to use in
      place of the TimelineWidget's default options.  Will overwrite
      the default options on a one-by-one basis.
      See defaultWidgetOptions for currently supported options.

**********************/
function TimelineWidget (
  container,
  fields,
  yLabel = '',
  widgetOptions = {}
) {
  this.fields = fields // used by WidgetServer

  const defaultWidgetOptions = {
    height: 400,
    maxPoints: 500
  }
  const thisWidgetOptions = { ...defaultWidgetOptions, ...widgetOptions }

  const colors = []
  let i = 0
  for (const id in fields) {
    colors.push(fields[id].color || d3.schemeCategory10[i++ % 10])
  }

  const widgetParams = {
    yLabel,
    colors,
    fieldNames: Object.keys(fields),
    fieldInfo: fields,
    ...thisWidgetOptions
  }

  const lineArr = {}
  for (const fieldName in fields) {
    lineArr[fieldName] = []
  }

  this.chart = realTimeLineChart(widgetParams)

  document.addEventListener('DOMContentLoaded', () => {
    d3.select(container).datum(lineArr).call(this.chart)
  })

  // When passed a websocket server /data report, sifts through
  // fields and updates any series with matching field names.
  this.process_message = function (message) {
    for (const fieldName in fields) {
      if (!message[fieldName] || message[fieldName].length === 0) {
        continue
      }

      const line = lineArr[fieldName]

      // Add each new point, converting sec to msec, and applying a transform, if defined.
      const f = fields[fieldName].transform
      message[fieldName].forEach(p => line.push({ time: p[0] * 1000, value: f ? f(p[1]) : p[1] }))

      const msecsToKeep = 1000 * fields[fieldName].seconds
      const tMax = line[line.length - 1].time
      const tMin = tMax - msecsToKeep
      while (line.length && line[0].time < tMin) {
        line.shift()
      }
      while (line.length > thisWidgetOptions.maxPoints) {
        line.shift()
      }
    }
    d3.select(container).datum(lineArr).call(this.chart)
  }
}

function realTimeLineChart (widgetParams) {
  const duration = 1000
  const { height, yLabel, colors, fieldNames, fieldInfo } = widgetParams
  const margin = { top: 20, right: 10, bottom: 20, left: yLabel ? 50 : 30 }

  function chart (selection) {
    selection.each(function (nodeData) {
      const totalNumPts = fieldNames.reduce((acc, v) => acc + nodeData[v].length, 0)
      if (totalNumPts === 0) return

      const width = this.clientWidth
      const w = width - margin.left - margin.right
      const h = height - margin.top - margin.bottom
      const data = fieldNames.map(fieldName => ({ fieldName, values: nodeData[fieldName] }))
      const t = d3.transition().duration(duration).ease(d3.easeLinear)
      const x = d3.scaleUtc().rangeRound([0, w])
      const y = d3.scaleLinear().rangeRound([h, 0])
      const z = d3.scaleOrdinal(colors)

      const xMin = d3.min(data, c => d3.min(c.values, d => d.time))
      const xMax = new Date(new Date(d3.max(data, c => d3.max(c.values, d => d.time)))
        .getTime() - (duration * 2))

      x.domain([xMin, xMax])
      y.domain([
        d3.min(data, c => d3.min(c.values, d => d.value)),
        d3.max(data, c => d3.max(c.values, d => d.value))
      ])
      z.domain(data.map(c => c.fieldName))

      const line = d3.line()
        .x(d => x(d.time))
        .y(d => y(d.value))

      let svg = d3.select(this).selectAll('svg').data([data])
      const gEnter = svg.enter().append('svg').append('g')
      gEnter.append('g').attr('class', 'axis x')
      gEnter.append('g').attr('class', 'axis y')
      gEnter.append('g').attr('class', 'units y')
        .append('text')
      gEnter.append('defs')
        .append('clipPath').attr('id', 'clip')
        .append('rect').attr('width', w).attr('height', h)
      gEnter
        .append('g').attr('class', 'lines').attr('clip-path', 'url(#clip)')
        .selectAll('.data').data(data).enter()
        .append('path').attr('class', 'data')

      const legendEnter = gEnter.append('g')
        .attr('class', 'legend')
        .attr('transform', 'translate(10,0)')
      legendEnter.selectAll('text')
        .data(data).enter()
        .append('text')
        .attr('y', (d, i) => (i * 20) + 5)
        .attr('x', 5)
        .attr('fill', d => z(d.fieldName))

      svg = selection.select('svg')
      svg.attr('width', width).attr('height', height)
      const g = svg.select('g')
        .attr('transform', 'translate(' + margin.left + ',' + margin.top + ')')

      g.select('g.axis.x')
        .attr('transform', 'translate(0,' + (height - margin.bottom - margin.top) + ')')
        .transition(t)
        .call(d3.axisBottom(x).ticks(d3.timeSecond.every(15)).tickFormat(d3.utcFormat('%H:%M:%S')))

      g.select('g.axis.y')
        .attr('transform', 'translate(' + w + ',0)')
        .transition(t)
        .attr('class', 'axis y')
        .call(d3.axisLeft(y)
          // Make tick marks span the whole chart, to function as grid lines.
          .tickSize(w)
        )
        .call(g => g.selectAll('.tick line')
          .attr('stroke-opacity', 0.2)
        )
        .call(g => g.selectAll('.tick text')
          .attr('dx', -10)
        )

      if (yLabel) {
        g.select('g.units.y')
          .attr('transform', 'translate(-40,' + (height - margin.bottom - margin.top) / 2 + ')')
          .select('text')
          .text(yLabel)
          .attr('text-anchor', 'middle')
          .attr('transform', 'rotate(-90)')
      }

      g.select('defs clipPath rect')
        .transition(t)
        .attr('width', w)
        .attr('height', height - margin.top - margin.right)

      g.selectAll('g path.data')
        .data(data)
        .style('stroke', d => z(d.fieldName))
        .style('stroke-width', 1)
        .style('fill', 'none')
        .transition()
        .duration(duration)
        .ease(d3.easeLinear)
        .on('start', tick)

      g.selectAll('g .legend text')
        .data(data)
        .text(d => {
          const legendName = fieldInfo[d.fieldName].name
          return legendName + (d.values.length > 0 ? ': ' + d.values[d.values.length - 1].value : '')
        })

      function tick () {
        d3.select(this)
          .attr('d', d => line(d.values))
          .attr('transform', null)

        const xMinLess = new Date(new Date(xMin).getTime() - duration)
        d3.active(this)
          .attr('transform', 'translate(' + x(xMinLess) + ',0)')
          .transition()
      }
    })
  }
  return chart
}

function DialWidget (container) {
  this.process_message = function (message) {
  }

  d3.select(container).append('text').text('Dial Widget coming soon')
}

export { TimelineWidget, DialWidget }

// The following default export allows
//     import d3_widgets from '../js/widgets/d3_widgets.js'
//     ...
//     widget_list.push(new d3_widgets.TimelineWidget(...))
// but that seems unnecessarily complicated for now.
export default { TimelineWidget, DialWidget }
