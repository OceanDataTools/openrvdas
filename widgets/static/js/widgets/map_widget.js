/*******************************************************************************
Create a map widget using Leaflet JS code (http://leafletjs.com).

See README.md for full documentation.

Sample invocation:

  <!-- Basic leaflet/jquery scripts. Leaflet's JS must come *after* is CSS. -->
  <script src="static/js/jquery/jquery-3.1.1.min.js"></script>
  <link rel="stylesheet" href="static/css/leaflet/leaflet.css" />
  <script src="static/js/leaflet/leaflet.js"></script>

  <!-- Widget-serving code -->
  <script src="map_widget.js"></script>
  <script src="widget_server.js"></script>

  <!-- Style sheet for this map demo -->
  <link rel="stylesheet" href="static/css/map_demo.css" />

  <div id="map_container">
    <div id="map">
    </div>
  </div>

  <script type="text/javascript">
    var widget_list = [new MapWidget('map', map_fields,
                                     fields_to_lat_lon,
                                     tile_server, map_overlays)];
    var widget_server = new WidgetServer(widget_list, 'localhost:8765');
    widget_server.serve();
  </script>

Based on code by Chris Romsos, Oregon State University RCRV project
*******************************************************************************/

var default_tile_server = {
    source: 'https://api.tiles.mapbox.com/v4/{id}/{z}/{x}/{y}.png?' +
        'access_token=pk.eyJ1IjoibWFwYm94IiwiYSI6ImNpejY4NXVycTA2e' +
        'mYycXBndHRqcmZ3N3gifQ.rJcFIG214AriISLbB6B5aw',
    attribution: 'Map data &copy; <a href="https://www.openstreetmap.org/">' +
        'OpenStreetMap</a> contributors, ' +
	'<a href="https://creativecommons.org/licenses/by-sa/2.0/">' +
        'CC-BY-SA</a>, Imagery © <a href="https://www.mapbox.com/">Mapbox</a>',
    id: 'mapbox.streets'
};

default_map_options = {
    initial_lat_lon: [0, 0],
    initial_zoom: 12,
    track_current: true,
    marker_options: {
        radius: 4,
        fillcolor: "#ff7800",
        color: "#000",
        weight: 1,
        opacity: 1,
        fillOpacity: 0.8
    }
};

function MapWidget(container, fields, fields_to_lat_lon,
                   tile_server=default_tile_server,
                   map_overlays=[],
                   map_options={}) {

    // Properties we need to store for later
    this.map = L.map(container);
    this.fields = fields;
    this.fields_to_lat_lon = fields_to_lat_lon;

    // Begin with defaults for map options, then override with the
    // ones that are passed in.
    this.map_options = default_map_options;
    for (var opt in map_options) {
        this.map_options[opt] = map_options[opt];
    }

    // Draw and situate the base layer
    this.map.setView(this.map_options.initial_lat_lon,
                     this.map_options.initial_zoom);
    if (tile_server.source) {
        L.tileLayer(tile_server.source, tile_server).addTo(this.map);
    }
    // Do we have additional layers? If we've just been given a single
    // source as a string, fold it into a list so we can handle uniformly.
    if (typeof(map_overlays) == 'string') {
        map_overlays = [map_overlays];
    }
    for (over_i = 0; over_i < map_overlays.length; over_i++) {
        $.getJSON(map_overlays[over_i],
                  function(data){
                      L.geoJSON(data).addTo(this.map);
                  }.bind(this)
                 );
    }
    //// Async version of geoJSON load commented out - is this any better
    //// than the getJSON call above?
    //
    //var map_json_query = $.ajax({
    //    url: geojson_source,
    //      dataType: 'json',
    //      success: console.log('Source ' + geojson_source + ' loaded successfully.'),
    //      error: function (xhr) {
    //        alert(xhr.statusText)
    //      }
    //});
    //$.when(map_json_query).done(function() {
    //    L.geoJSON(map_json_query.responseJSON).addTo(this.map);
    //}.bind(this));

    // Gets called when websocket server finds updates to the fields
    // we're interested in.
    this.process_message = function(message) {
        if (!this.map) {
            console.log('No map! Skipping update');
            return;
        }
        // First, collate the fields we're interested in by timestamp
        var ts_array = {}
        for (var field_name in this.fields) {
            if (! message[field_name]) {
                continue;
            }
            var ts_pair_list = message[field_name];
            for (var pair_i = 0; pair_i < ts_pair_list.length; pair_i++) {
                var ts_pair = ts_pair_list[pair_i];
                var ts = ts_pair[0], value = ts_pair[1];
                if (ts_array[ts] === undefined) {
                    ts_array[ts] = {};
                }
                ts_array[ts][field_name] = value;
            }
        }
        // Now go through in timestamp order, adding geo points
        var sorted_ts = Object.keys(ts_array).sort();
        for (var ts_i = 0; ts_i < sorted_ts.length; ts_i++) {
            var ts = sorted_ts[ts_i],
                lat_lon = this.fields_to_lat_lon(ts_array[ts]);
            if (this.map_options.track_current) {
                this.map.setView(lat_lon);
            }
            // A hand-crafted bit of geoJSON to wrap our lat_lon point
            var points = {"type":"FeatureCollection",
                          "features":[
                              {"id":1,"type":"Feature",
                                       "geometry":{
                                           "type":"Point",
                                           "coordinates":[lat_lon[1],
                                                          lat_lon[0]]}}
                          ]
                         };
            L.geoJson(points, {
                pointToLayer: function (feature, latlng) {
                    return L.circleMarker(latlng,
                                          this.map_options.marker_options);
                }.bind(this)
            }).addTo(this.map);
        }
    }.bind(this);
}
