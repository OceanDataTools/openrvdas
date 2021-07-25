# OpenRVDAS
© David Pablo Cohn - david.cohn@gmail.com  
DRAFT 2018-08-09

The Open Research Vessel Data Acquisition System (OpenRVDAS) is a software framework used for building custom data acquisition systems (DAS). OpenRVDAS target audiences are oceanographic research vessel operators and operators of other science-related platforms that have the need to record streaming data. OpenRVDAS is capable of reading data records from serial ports and network-aware sensors, optionally modifying those data records and streaming either the result to one or more destinations, including logfiles, network ports, databases, etc.

OpenRVDAS is designed to be modular and extensible, relying on simple composition of Readers, Transforms and Writers to achieve the needed datalogging functionality.

The project code repository is at [https://github.com/oceandatatools/openrvdas](https://github.com/oceandatatools/openrvdas).

Please see the [OpenRVDAS Introduction and Overview](intro_and_overview.md), the [Introduction to Loggers](intro_to_loggers.md) and [Controlling Loggers](controlling_loggers.md) to get started.

Other relevant documents are:

* [The Listener Script - listen.py](listen_py.md) - how to use OpenRVDAS's core utility script
* [Configuration Files](configuration_files.md) - how to define configuration files to simplify running loggers with listen.py
* [OpenRVDAS Components](components.md) - what components exist and what they do
* [Simulating Live Data](simulating_live_data.md) - using the simulate_data.py script to simulate a live system using stored data for development and testing
* [OpenRVDAS Django Web User Interface](django_interface.md) - an introduction to the web-based GUI
* [Grafana/InfluxDB-based Displays](grafana_displays.md) - an introduction to using InfluxDB and Grafana for displaying data
* [Parsing](parsing.md) - how to work with the included RecordParser to turn raw text records into structured data fields
* [Security assumptions](security.md) - the (rather naive) security assumptions made about the environment in which OpenRVDAS runs.

A very rudimentary project website is available at [OpenRVDAS.org](http://openrvdas.org)

**DISCLAIMER**: THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF
ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE,
INCLUDING INJURY, LOSS OF LIFE, PROPERTY, SANITY OR CREDIBILITY AMONG
YOUR PEERS WHO WILL TELL YOU THAT YOU REALLY SHOULD HAVE KNOWN BETTER.
