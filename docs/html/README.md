# OpenRVDAS Logger Component HTML Documents
© David Pablo Cohn - david.cohn@gmail.com  
2019-09-03

The following directories of documentation are best accessed by pointing your browser directly at
the files in your local copy of the repository:

 - [Logger component documentation here](logger/index.html)
 - [Server component documentation here](server/index.html)

The documents in this directory were generated automatically by [pdoc](https://pdoc3.github.io/pdoc/) using the commands:

```
pip3 install pdoc

# Generate docs for logger components and some server scripts
pdoc3 --html -o docs/html logger
pdoc3 -f --html --filter logger_,server_api,cached -o docs/html server

# Get rid of docs for all test_*.py files
rm docs/html/logger/*/test_*.html docs/html/server/test_*.html
sed -i '' '/test_/d' docs/html/logger/*/index.html docs/html/server/index.html
```
