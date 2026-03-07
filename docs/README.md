# OpenRVDAS
© David Pablo Cohn - david.cohn@openrvdas.org  
2026-03-07

This directory contains documentation, and pointers to full project documentation, for [OpenRVDAS](https://openrvdas.org), a part of the [Ocean Data Tools project](http://oceandata.tools).

The Open Research Vessel Data Acquisition System (OpenRVDAS) is a software framework used for building custom data acquisition systems (DAS). OpenRVDAS target audiences are oceanographic research vessel operators and operators of other science-related platforms that have the need to record streaming data. OpenRVDAS is capable of reading data records from serial ports and network-aware sensors, optionally modifying those data records and streaming either the result to one or more destinations, including logfiles, network ports, databases, etc.

OpenRVDAS is designed to be modular and extensible, relying on simple composition of Readers, Transforms and Writers to achieve the needed datalogging functionality.

The project code repository is at [https://github.com/oceandatatools/openrvdas](https://github.com/oceandatatools/openrvdas).

## Documentation

### Full project documentation

**Online:** The full OpenRVDAS documentation is hosted online at **[https://www.oceandatatools.org/openrvdas-docs/](https://www.oceandatatools.org/openrvdas-docs/)**.

**Offline/locally:** Source code for the documentation is maintained as a separate Jekyll-based site at
[https://github.com/oceandatatools/openrvdas-docs](https://github.com/oceandatatools/openrvdas-docs).

To browse the documentation locally/offline, follow the instructions in [the GitHub repository's README.md file](https://github.com/OceanDataTools/openrvdas-docs/blob/master/README.md) to clone the GitHub repository install and run Jekyll. Once running, it will be available at [http://localhost:4000](http://localhost:4000).

### Component API reference

Auto-generated API documentation for all OpenRVDAS logger and server components
is located in [`docs/html/`](html/index.html). Open **[html/index.html](html/index.html)**
in a browser to browse the Readers, Transforms, Writers, and server modules.

This documentation is generated directly from the source code and is fully
self-contained (no internet connection required). It is automatically regenerated
whenever Python source files are pushed to the `dev` branch.

To regenerate the component API reference documentation manually, run:

```bash
./docs/generate_html_docs.sh
```


**DISCLAIMER**: THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF
ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE,
INCLUDING INJURY, LOSS OF LIFE, PROPERTY, SANITY OR CREDIBILITY AMONG
YOUR PEERS WHO WILL TELL YOU THAT YOU REALLY SHOULD HAVE KNOWN BETTER.
