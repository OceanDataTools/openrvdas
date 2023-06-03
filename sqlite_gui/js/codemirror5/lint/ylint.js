// CodeMirror, copyright (c) by Marijn Haverbeke and others
// Distributed under an MIT license: https://codemirror.net/5/LICENSE

(function(mod) {
  if (typeof exports == "object" && typeof module == "object") // CommonJS
    mod(require("../../lib/codemirror"));
  else if (typeof define == "function" && define.amd) // AMD
    define(["../../lib/codemirror"], mod);
  else // Plain browser env
    mod(CodeMirror);
})(function(CodeMirror) {
"use strict";

// Depends on js-yaml.js from https://github.com/nodeca/js-yaml

// declare global: jsyaml

CodeMirror.registerHelper("lint", "yaml", async function(text) {
  var found = [];
//  if (!window.yproxy) {
//    if (window.console) {
//      window.console.error("Error: window.jsyaml not defined, CodeMirror YAML linting cannot run.");
//    }
//    return found;
//  }
  if (!window.yproxy) {
    return found;
  }
  var f = await yproxy(text)[0];
      
  var bad_stuff = f.split(',');
  var first_err = bad_stuff[0];
  var from = first_err.split(':')[0] + ':';
  from  += first_err.split(':')[1];
  var message = first_err.split(' ');

  var e = {
      'from': from,
      'to': from,
      'message': message
  }

  //var loc = e.mark,
      // js-yaml YAMLException doesn't always provide an accurate lineno
      // e.g., when there are multiple yaml docs
      // ---
      // ---
      // foo:bar
  //from = loc ? CodeMirror.Pos(loc.line, loc.column) : CodeMirror.Pos(0, 0),
  //to = from;
  found.push({ from: from, to: to, message: e.message });
  return found;
});

});
