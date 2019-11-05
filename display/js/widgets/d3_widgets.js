/*******************************************************************************
D3 based widgets (http://d3js.com)

This file defines and exports two basic widgets:
  - TimelineWidget
  - DialWidget
********************************************************************************/

// https://standardjs.com/#i-use-a-library-that-pollutes-the-global-namespace-how-do-i-prevent-variable-is-not-defined-errors
/* global d3 */

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

/**********************
// DialWidget definition

Create a D3 based dial displaying one or more variables

  container - name of div on page to use for displaying widget

  fields - associative array of field_name:{options} for widget

  widget_options - an optional associative array of options to use in
      place of the DialWidget's default options. Will overwrite the default
      options on a one-by-one basis.
      See defaultWidgetOptions for currently supported options.
**********************/
function DialWidget (
  container,
  fields,
  widgetOptions = {}
) {
  this.fields = fields // used by WidgetServer

  const defaultWidgetOptions = {
    min: 0,
    max: 360,
    startAngle: 0,
    endAngle: 360,
    tickInterval: 45,
    minorTickInterval: 5,
    radius: 180,
    showDescriptions: false,
    showNumericValues: true
  }
  const thisWidgetOptions = { ...defaultWidgetOptions, ...widgetOptions }

  const colors = []
  const fieldNames = []
  let i = 0
  for (const id in fields) {
    colors.push(fields[id].color || d3.schemeCategory10[i++ % 10])
    fieldNames.push(fields[id].name)
  }

  const vMin = thisWidgetOptions.min
  const vMax = thisWidgetOptions.max
  const aMin = thisWidgetOptions.startAngle
  const delta = thisWidgetOptions.endAngle - thisWidgetOptions.startAngle
  // force aMax to be > aMin and <= aMin + 360, by adding a multiple of 360 to endAngle
  const aMax = thisWidgetOptions.endAngle + 360 * Math.floor((360 - delta) / 360)
  const vScale = (aMax - aMin) / (vMax - vMin)

  document.addEventListener('DOMContentLoaded', () => {
    this.initialize()
  })

  this.initialize = function () {
    const r = defaultWidgetOptions.radius
    const svg = d3.select(container)
      .append('svg')
      .attr('class', 'gauge')
      .attr('width', r * 2)
      .attr('height', r * 2)

    svg.append('circle').attr('cx', r).attr('cy', r).attr('r', r - 1).attr('class', 'outer')
    svg.append('circle').attr('cx', r).attr('cy', r).attr('r', r - 8).attr('class', 'inner')
    svg.append('path')
      .attr('class', 'arc')
      .attr('d', d3.arc()({
        startAngle: aMin * Math.PI / 180,
        endAngle: aMax * Math.PI / 180,
        innerRadius: r - 8,
        outerRadius: r - 8
      }))
      .attr('transform', `translate(${r}, ${r})`)
    svg.append('path')
      .attr('class', 'wedge')
      .attr('d', d3.arc()({
        startAngle: aMax * Math.PI / 180,
        endAngle: 2 * Math.PI + aMin * Math.PI / 180,
        innerRadius: 0,
        outerRadius: r - 1
      }))
      .attr('transform', `translate(${r}, ${r})`)

    if (thisWidgetOptions.showNumericValues || thisWidgetOptions.showDescriptions) {
      // add text fields for descriptions and/or numeric values
      svg.selectAll('text.numeric').data(colors).enter()
        .append('text')
        .attr('class', 'numeric')
        .attr('fill', d => d)
        .attr('text-anchor', 'middle')
        .attr('x', r)
        .attr('y', (d, i) => r + 50 + (i * 20))
    }

    /* eslint-disable key-spacing */
    const pointerPath = [
      { x: -5, y: -110 },
      { x:  0, y: -140 },
      { x:  5, y: -110 },
      { x:  5, y:   10 },
      { x: -5, y:   10 },
      { x: -5, y: -110 }
    ]
    /* eslint-enable key-spacing */

    svg.selectAll('g').data(colors).enter()
      .append('g')
      .style('fill', d => d)
      .selectAll('path')
      .data([pointerPath])
      .enter()
      .append('path')
      .attr('class', 'pointer')
      .attr('d', d3.line().x(d => d.x).y(d => d.y))
      .attr('transform', `translate(${r}, ${r})`)

    svg.append('circle').attr('cx', r).attr('cy', r).attr('r', 5).attr('class', 'pin')

    const tickAngles = []
    const minorTickAngles = []
    const delta = thisWidgetOptions.tickInterval * vScale
    const delta2 = thisWidgetOptions.minorTickInterval * vScale
    for (let a = aMin; a <= aMax; a += delta) {
      tickAngles.push(a)
      for (let a2 = a + delta2; a2 < a + delta && a2 < aMax; a2 += delta2) {
        minorTickAngles.push(a2)
      }
    }
    if (aMax - aMin === 360) { tickAngles.shift() } // avoid overlapping labels

    // each major tick consists of a group with a line and a label, moved as a unit
    const tickGroups = svg.selectAll('line').data(tickAngles).enter().append('g')
      .attr('class', 'major')
    tickGroups.append('line')
      .attr('x1', 0).attr('y1', -162)
      .attr('x2', 0).attr('y2', -172)
    tickGroups.append('text')
      .text(d => vMin + (d - aMin) / vScale)
      .attr('y', -150)
      .attr('text-anchor', 'middle')
    tickGroups.attr('transform', d => `translate(${r}, ${r})rotate(${d})`)

    // create and position the minor ticks
    svg.selectAll('line.minor').data(minorTickAngles).enter()
      .append('line')
      .attr('class', 'minor')
      .attr('x1', 0).attr('y1', -167)
      .attr('x2', 0).attr('y2', -172)
      .attr('transform', d => `translate(${r}, ${r})rotate(${d})`)

    if (thisWidgetOptions.showNumericValues && !thisWidgetOptions.showDescriptions) {
      // add tooltip for numeric display
      const div = d3.select(container).append('div').attr('class', 'tooltip')
      svg.selectAll('text.numeric')
        .on('mouseover', (d, i) =>
          div.style('opacity', 0.8)
            .html(fieldNames[i])
            .style('color', colors[i])
            .style('border-color', colors[i])
            .style('left', `${d3.event.pageX - 0.7 * r}px`)
            .style('top', `${d3.event.pageY - 0.7 * r}px`)
        )
        .on('mouseout', (d, i) => div.style('opacity', 0))
    }

    // scale the whole widget to the specified radius
    svg.attr('transform', d => `scale(${thisWidgetOptions.radius / defaultWidgetOptions.radius})`)
  }

  this.process_message = function (message) {
    const data = []
    for (const fieldName in fields) {
      const arr = message[fieldName]
      if (!arr || arr.length === 0) {
        continue
      }

      // Take the last value, and apply a transform, if defined.
      const v = arr[arr.length - 1][1]
      data.push(fields[fieldName].transform ? fields[fieldName].transform(v) : v)
    }

    // The default radius is used here because the svg element has a transform attribute
    // that scales to the specified radius.
    const r = defaultWidgetOptions.radius

    // transition pointers to new positions
    d3.select(container)
      .selectAll('path.pointer').data(data)
      .transition()
      .duration(250)
      // using 'function' instead of arrow so that 'this' will refer to the current DOM element
      .attrTween('transform', function (d) {
        let targetRotation = aMin + (d - vMin) * vScale
        const currentRotation = this.previousRotation || targetRotation
        this.previousRotation = targetRotation

        if (aMax - aMin === 360) {
          // minimize movement needed to reach target
          if (targetRotation - currentRotation > 180) { targetRotation -= 360 }
          if (targetRotation - currentRotation < -180) { targetRotation += 360 }
        }

        return t => {
          const intermediateRotation = currentRotation + (targetRotation - currentRotation) * t
          return `translate(${r}, ${r})rotate(${intermediateRotation})`
        }
      })

    if (thisWidgetOptions.showNumericValues || thisWidgetOptions.showDescriptions) {
      // update descriptions and/or numeric values
      d3.select(container)
        .selectAll('text.numeric').data(data)
        .text((d, i) =>
          thisWidgetOptions.showDescriptions
            ? `${fieldNames[i]}${thisWidgetOptions.showNumericValues ? ': ' + d : ''}`
            : d
        )
    }
  }
}

export { TimelineWidget, DialWidget }

// The following default export allows
//     import d3_widgets from '../js/widgets/d3_widgets.js'
//     ...
//     widget_list.push(new d3_widgets.TimelineWidget(...))
// but that seems unnecessarily complicated for now.
export default { TimelineWidget, DialWidget }
