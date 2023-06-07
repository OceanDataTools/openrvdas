### What is OpenRVDAS
Read up on the parent project [here](https://github.com/OceanDataTools/openrvdas)

### OpenRVDAS Sqlite GUI
The purpose I had in mind when I created this was a lighter API than
Django for use on headless and embeddedi (like Raspberry Pi ZeroW), but 
once I got thinking about it, I decided that there was no reason it could 
not have a GUI, too.

And this project was born.

### The API
Implements the ServerAPI from OpenRVDAS, the datastore being a SQLite
database.  We don't bother with fine-grained tables, foreign keys,
or search indexes.  We use the in-memory object and standard python
dictionary methods for all reads, and on any change just write the entire
object to the datastore. 
To guard against our in-memory copy being stale, we compare timestamps between 
the two instances.

### The GUI
The GUI isn't necessary to operate OpenRVDAS in sqlite mode.  There's a 
utility script (api_tool.py) that can be used interactively or in single
command mode by entering the command as an argument.  For those familiar 
with OpenRVDAS, it performs the same function (in much the same way) as
server_command_line.py.
Slightly improved aesthetics and a much more transparent operations model
make the SQLite GUI easier to customize to your needs.


