# OpenRVDAS Logger Component HTML Documents
© David Pablo Cohn - david.cohn@gmail.com  
2019-09-03

This directory contains automatically-generated HTML documentation for OpenRVDAS logger components and servers.  It is best viewed by viewing [the directory's index.html page](https://htmlpreview.github.io/?https://github.com/oceandatatools/openrvdas/blob/master/docs/html/index.html).

The documents in this directory were generated automatically by [pdoc](https://pdoc3.github.io/pdoc/) using the commands:

```
pip3 install pdoc3

# Generate docs for logger components and some server scripts
pdoc3 --force --html -o docs/html logger
pdoc3 --force --html --filter logger_,server_api,cached -o docs/html server

# Get rid of docs for all test_*.py files
rm docs/html/logger/*/test_*.html docs/html/server/test_*.html
sed -i '' '/test_/d' docs/html/logger/*/index.html docs/html/server/index.html
```
