# OpenRVDAS
© David Pablo Cohn - david.cohn@openrvdas.org  
2026-03-07

The Open Research Vessel Data Acquisition System (OpenRVDAS) is a software framework used for building custom data acquisition systems (DAS). OpenRVDAS target audiences are oceanographic research vessel operators and operators of other science-related platforms that have the need to record streaming data. OpenRVDAS is capable of reading data records from serial ports and network-aware sensors, optionally modifying those data records and streaming either the result to one or more destinations, including logfiles, network ports, databases, etc.

OpenRVDAS is designed to be modular and extensible, relying on simple composition of Readers, Transforms and Writers to achieve the needed datalogging functionality.

The project code repository is at [https://github.com/oceandatatools/openrvdas](https://github.com/oceandatatools/openrvdas).

## Documentation

### Full project documentation

The full OpenRVDAS documentation is hosted online at **[http://www.oceandatatools.org/openrvdas-docs/](http://www.oceandatatools.org/openrvdas-docs/)**.

It is maintained as a separate Jekyll-based site at
[https://github.com/oceandatatools/openrvdas-docs](https://github.com/oceandatatools/openrvdas-docs).  To browse the documentation locally, clone that repository and follow the setup instructions in its [INSTALL.md](https://github.com/OceanDataTools/openrvdas-docs/blob/master/install.md). Once running, it will be available at [http://localhost:4000](http://localhost:4000).

### Component API reference

Auto-generated API documentation for all OpenRVDAS logger and server components
is located in [`docs/html/`](file://html/index.html). Open **[html/index.html](file://html/index.html)**
in a browser to browse calling conventions for all Readers, Transforms, Writers, and server modules in the repository.

This documentation is generated directly from the source code and is fully
self-contained (no internet connection required). It is automatically regenerated
whenever Python source files are pushed to the `dev` branch.

To regenerate it manually:

```bash
./docs/generate_html_docs.sh
```

## Where to start?
* [OpenRVDAS Quickstart](http://www.oceandatatools.org/openrvdas-docs/quickstart/) if you want to just grab the code and poke around with basic loggers as quickly as possible.
* [GUI Quickstart](http://www.oceandatatools.org/openrvdas-docs/quickstart_gui/) if you want to play with the web-based interface.

Other relevant documents are:

* [The Listener Script - listen.py](http://www.oceandatatools.org/openrvdas-docs/listen_py/) - how to use OpenRVDAS's core utility script
* [Configuration Files](http://www.oceandatatools.org/openrvdas-docs/logger_configuration_files/) - how to define configuration files to simplify running loggers with listen.py
* [OpenRVDAS Components](http://www.oceandatatools.org/openrvdas-docs/components/) - what components exist and what they do
* [Simulating Live Data](http://www.oceandatatools.org/openrvdas-docs/simulating_live_data/) - using the simulate_data.py script to simulate a live system using stored data for development and testing
* [Grafana/InfluxDB-based Displays](http://www.oceandatatools.org/openrvdas-docs/grafana_displays/) - an introduction to using InfluxDB and Grafana for displaying data
* [Parsing](http://www.oceandatatools.org/openrvdas-docs/parsing/) - how to work with the included RecordParser to turn raw text records into structured data fields
* [Security assumptions](http://www.oceandatatools.org/openrvdas-docs/security/) - the (rather naive) security assumptions made about the environment in which OpenRVDAS runs.

OpenRVDAS is a part of the [Ocean Data Tools project](http://oceandata.tools).

**DISCLAIMER**: THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF
ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE,
INCLUDING INJURY, LOSS OF LIFE, PROPERTY, SANITY OR CREDIBILITY AMONG
YOUR PEERS WHO WILL TELL YOU THAT YOU REALLY SHOULD HAVE KNOWN BETTER.
