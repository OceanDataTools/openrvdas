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
  var f = {};
  try {
      var f = await yproxy(text);
  } catch (e) {};
  var lintErrors = f.lint;
  if (!lintErrors) { return found; } 
  for (var index in lintErrors) {
      var thisError = lintErrors[index];
      var from = CodeMirror.Pos(thisError.line - 1, thisError.column);
      var to = from;
      var severity = thisError.severity;
      found.push({from: from, to: to, message: thisError.message, severity: severity });
  }    
  // console.log(f)
  // var e = {
  //    'from': from,
  //    'to': from,
  //    'message': message
  //}

  //var loc = e.mark,
      // js-yaml YAMLException doesn't always provide an accurate lineno
      // e.g., when there are multiple yaml docs
      // ---
      // ---
      // foo:bar
  //from = loc ? CodeMirror.Pos(loc.line, loc.column) : CodeMirror.Pos(0, 0),
  //to = from;
  //found.push({ from: from, to: to, message: e.message });
  return found;
});

});
