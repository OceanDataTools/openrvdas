// 
// XMLRPC
//
//     Function/Class to handle XML-RPC.  Not sure how generalized it
//     is since I constructed it to work with the XML-RPC from
//     Supervisor (as part of OpenRVDAS)
//
//     Exports two functions:
//         createXML(command [,param]) - creates the XMLRPC request body
//         parse(txt) - parses the returned text and returns an object
//
var XMLRPC = (function() {
    //
    // create_xml(command, [params])
    //     Create an XML-RPC request body
    function createXML(command) {
        var r = "";
        r = r + "<?xml version='1.0'?>";
        r = r + "<methodCall>";
        r = r + "<methodName>";
        r = r + command;
        r = r + "</methodName>";
        r = r + "<params>";
        if (typeof arguments[1] !== 'undefined') {
            // we can cheat here because our (only) arg *is* string
            r = r + "<param><value><string>"
            r = r + arguments[1];
            r = r + "</string></value></param>";
        }
        r = r + "</params>";
        r = r + "</methodCall>";
        return r;
    }

    // internal use by parse()
    function _querySelector(node, selector) {
        var a = selector.split(" ")
        for (var i in a) {
            node = _firstChildByTagName(node, a[i])
            if (!node)
                break;
        }
        return node
    }

    // internal use by parse()
    function _firstChildByTagName(node, name) {
        for (var i=0; i<node.childNodes.length; i++) {
            if (node.childNodes[i].tagName === name) {
                return node.childNodes[i]
            }  
        }
    }

    // internal use by parse()
    function _firstChildNode(node) {
        for (var i=0; i<node.childNodes.length; i++) {
            if (node.childNodes[i].nodeType === 1) {
                return node.childNodes[i]
            }
        }
    }

    // internal use by parse()
    // NOTE:  Not a full parser, just what we need to Supervisor's XML-RPC
    //        Well.. maybe a little more.
    function _parseValue(node) {
        var type_node = _firstChildNode(node)
        switch (type_node.tagName) {
            case 'array': 
                var res = []
                var data = _firstChildByTagName(type_node, "data")
                for (var i=0; i<data.childNodes.length; i++) {
                    var value = data.childNodes[i]
                    if (value.tagName === 'value') {
                        res.push(_parseValue(value))
                    }
                }
                return res
            case 'boolean':
                return type_node.firstChild.data !== '0' || type_node.firstChild.data === 'true'
            case 'double':
                break;
            case 'i4':
            case 'int':
                break;
            case 'string':
                return type_node.firstChild ? type_node.firstChild.data : undefined
            case 'struct':
                var res = {}
                for (var i=0; i<type_node.childNodes.length; i++) {
                    var member = type_node.childNodes[i]
                    if (member.tagName === 'member') {
                        res[_firstChildByTagName(member, "name").firstChild.data] =
                                _parseValue(_firstChildByTagName(member, "value"))
                    }
                }
                return res
            case 'nil':
                break
            default:
                break
        }
    }

    // Function takes a string, creates an XMLDom tree, and parses it
    // into something that's easy for javascript to deal with.
    function parse(xml_text) {
        var parser = new DOMParser();
        var xmlDoc = parser.parseFromString(xml_text, "application/xml");
        var errorNode = xmlDoc.querySelector("parsererror");
        if (errorNode) {
            console.log("Parse failed");
        }
        e = xmlDoc.documentElement;
        try {
            if (e.firstChild.tagName === 'fault') {
                throw new Error("TODO: XML-RPC fault")
            }
            return _parseValue(_querySelector(e, "params param value"))
        }
        catch (e) {
            throw new Error("Error parsing XML-RPC response")
        }
    }

    return {
        parse: parse,
        createXML: createXML
    }


})();

//
// Supervisor
//
//   Object/Class that queries the supervisord XML-RPC interface,
//   and populates a table (if it exists) with status information
//   on the processes defined in the supervisor config.
var Supervisor = (function() {

    // FIXME:  This value should be configurable
    var url = "https://" + document.location.host + ":9000/RPC2";

    var query_Supervisor = async function(method, args) {
        var post_options = {
            method: 'POST',
            body: XMLRPC.createXML(method, args),
            headers: { 'Content-Type': 'text/xml' }
        }
        try {
            var post = await fetch(url, post_options);
        } catch (error) {
            console.error(error);
            return '{}';
        }
        if (!post.ok) {
            // construct an error object
            throw new Error("Supervisor XML-RPC POST not OK");
        } 
        var t = await post.text();
        try {
            var j = XMLRPC.parse(t)
            // console.log("XMLRPC: ", j);
            return j;
        } catch (error) {
            console.error(error);
            return '{}';
        }
    }

    var create_element = function(name, status) {
        var tbl = document.getElementById('daemon-table');
        if (!tbl) { return; }
        var tr = document.getElementById('daemon-row');
        if (!tr) { 
            tr = document.createElement('tr');
            tr.setAttribute('id', 'daemon-row');
            tbl.appendChild(tr);
        }
        if (name.includes(':')) {
            name = name.split(':')[1];
        }
        var td = document.getElementById(name + "_status");
        if (!td) {
            td = document.createElement('td');
            td.setAttribute('id', name + "_status");
            td.innerHTML = name;
            tr.appendChild(td);
        }
        if (status == "RUNNING") {
            td.className = 'text-success';
        } else if (status == "FATAL") {
            td.className = 'text-danger';
        } else {
            td.className = 'text-warning';
        }
    }
     
    // Updates the daemon status every 10 seconds
    async function keep_updating() {
        // Get updates
        var AllStatus = await query_Supervisor('supervisor.getAllProcessInfo');
        for (i in AllStatus) {
            var o = AllStatus[i];
            var name = o.name + '_status';
            var td = document.getElementById(name);
            if (td) {
                if (o.statename == "RUNNING") {
                    td.className = 'text-success';
                } else if (o.statename == "FATAL") {
                    td.className = 'text-danger';
                } else {
                    td.className = 'text-warning';
                }
            }
        }
        setTimeout(keep_updating, 10000)
    }

   
    // Queries supervisor XML-RPC for the processes it manages and
    // populates some status information on the webpage.
    // This function will *not* pick up on changes to the supervisor
    // config.  I mean, it could, but that seems excessive.  You can
    // just reload the page.
    var do_stuff = async function() {
        // FIXME:  We should make sure we're talking to 
        //         *supervisor*'s XMLRPC by getting identification.
        //         supervisor.getIdentification
        var APIVersion = await query_Supervisor('supervisor.getAPIVersion');
        if (APIVersion != 3) {
            console.warn("Supervisor XML-RPC version is not 3");
        }

        var AllStatus = await query_Supervisor('supervisor.getAllProcessInfo');

        var i, status;
        var daemons = [];
        for (i in AllStatus) {
            var o = AllStatus[i];
            var name = o.group + ":" + o.name;
            daemons.push(name);
            create_element(name, o.statename);
            console.log(name, "-->", o.statename);
        }
        // Now call a function, and afterwards set a TimeOut to call it again.
        keep_updating(daemons);
    }

    try {
        do_stuff();
    } catch {
        console.log('Some error occurred in Supervisor');
    }

    return {
        // method: method
    }
})();
