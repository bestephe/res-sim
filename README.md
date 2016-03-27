# res-sim
The simulation environment used to evaluate implementations of Plinko,
ADST, EDST, DF-EDST, and DF-FI resilience.

## Overview

This simulation environment was used to evaluate the following
publications:

1. "Plinko: Building Provably Resilient Forwarding Tables" in HotNets 2013
   [(PDF)](http://conferences.sigcomm.org/hotnets/2013/papers/hotnets-final11.pdf)

2. "Handling Congestion and Routing Failures in Data Center Networking."
   PhD Thesis, Rice University, 2015
   [(PDF)](http://pages.cs.wisc.edu/~brentstephens/docs/thesis.pdf)

3. "Scalable Multi-Failure Fast Failover via Forwarding Table
   Compression" from SOSR 2016
   [(PDF)](http://pages.cs.wisc.edu/~brentstephens/docs/plinko.sosr16.pdf)

4. "Deadlock-Free Local Fast Failover for Arbitrary Data Center
   Networks" from Infocom 2016
   [(PDF)](http://pages.cs.wisc.edu/~brentstephens/docs/edst.infocom16.pdf)

**TODO: Add these PDFs to the repository to ensure their availability.**

The programs in this repository are made available for two reasons: One,
to allow the research in these papers two be verifiable, and two,
because they may be useful to other people.  However, there are some
limitations to these programs.  As a result of this code base evolving
organically over time, the code quality is often not high.  Duplicated
and copy/pasted code exists, as does stale code.  Similarly, some of the
data file formats are poorly designed, and data files can easily grow to
be very large.  Further, due to a poor early design choice for ease of
development for an initial prototype, performance can be quite slow.
Although relying on the igraph library speeds up graph computation,
there is additional computation that still constraints execution time
because it is implemented in python.  However, I do not expect that
reimplementing the functions provided by this simulation environment
would be that difficult.

### Installation 

The following instructions have been tested to correctly build the
system on a default installation of Ubuntu 14.04.

First, run the following command to install prerequisite packages:
```
sudo apt-get install bison flex build-essential python-yaml python-simplejson python-igraph libxml2-dev python-numpy python-scipy python-argparse
```

Next, although some later versions of Ubuntu have `python-ijson`
included in the default repositories (`sudo apt-get install
python-ijson`), this is no the case on Ubuntu 14.04.  Instead, run
```
sudo apt-get install python-pip
sudo pip install ijson
```

**NOTE: Using a patched version of igraph is crucial to being able to
duplicate results.** Next, this environment depends on a custom version
of igraph (See
[igraph-0.6.5/resnet_igraph-0.6.5.patch](igraph-0.6.5/resnet_igraph-0.6.5.patch)).
Most notably, this version of igraph adds in randomization to some of
the graph traversal algorithms.   To build and install this, do the
following:
```
$ cd igraph-0.6.5/
$ ./configure
$ make
$ sudo make install
```


### A quick tour of the environment

The scripts in this simulation environment can be divided up by the
tasks they perform.  The major tasks are as follows:

1. Generating topologies
2. Forwarding table state computation, which includes building
   forwarding tables, compressing forwarding tables, and computing the
   state required for a forwarding table
3. Outputting forwarding tables to data files
4. Computing throughput and estimating the expected probability of routing failure
5. Running multiple instances of other programs
7. Estimating the probability of routing failure and total forwarding table state

#### Generating Topologies

The three major scripts for generating topologies are `topo_opt.py`,
`topo_gen.py`, and `gen_topos.sh`.  First, `topo_opt.py` computes the
configuration of a generalized fat tree, hyperx (flattened butterfly and
hypertorus), or jellyfish topology that contains the fewest possible
number of switches given a number of hosts, bisection
bandwidth, and switch radix specified by command line arguments. Next,
`topo_gen.py` generates a topology according to the configuration
outputted by `topo_opt.py`.  Finally, `gen_topos.sh` contains the calls
to `topo_opt.py` and `topo_gen.py` needed to generate topologies of the
size and bisection bandwidths used in the papers mentioned above.
However, because `topo_gen.py` uses randomization, these will not be the
exact same topologies used in these papers.  After running,
`gen_topos.sh` will place topologies in the folders BX, where the
normalized bisection bandwidth of the topologies in folder BX is equal
to 1/X.

#### State Computation

The major scripts for computing forwarding table state are
`resnet_alg.py` and `tree_alg.py`, which compute forwarding tables for
failure identifying resilience and EDST/ADST resilience, respectively.
The usage output for these programs is helpful, and there are example
calls to these programs in many of the `run_*.py` scripts.  For failure
identifying resilience, it is possible to build routes that either
protect against edge failures or vertex failures.

#### Outputting Forwarding Tables

The two programs for computing forwarding table state can also output
forwarding tables to files.  Because current YAML libraries load the
entire file into memory before parsing, the tables are stored in JSON.
`tables/build_tables.sh` is the main file for generating Plinko or FCP
forwarding tables (MPLS-FRR is omitted because the routes of Plinko will
be the same).  **Note: forwarding tables are topology specific.  This
implies that regenerating topologies requires that all forwarding tables
are also regenerated.  Although the EGFT and HyperX topology generator
should be deterministic, the Jellyfish topologies will differ each time
they are generated.**

#### Computing Throughput and the Probability of Routing Failure

The two main programs for computing both the probability of a routing
failure, stretch, and  throughput given a collection of forwarding
tables for a topology are `resnet_throughput.py` and
`tree_throughput.py`, which compute throughput for failure identifying
resilience and EDST/ADST resilience, respectively.  Currently, only a
uniform random workload is supported, although two different failure
models are implemented.   These programs require both a topology and
forwarding tables that were generated for that same topology.  As
before, the usage information for these scripts is helpful, and there
are example calls to these programs in many of the `run*_throughput.py`
scripts.

#### Running Other Programs

There are many meta-programs for running multiple instances of other
programs in parallel. The first of such meta-programs, `run_sim.sh` is
written in BASH and is used to compute forwarding table state for
different algorithms.  The rest of these programs are written in Python
and follow the naming convention of `run_*.py`.  Although these programs
were meant to be self-explanatory in their names, there is often too
much copying and pasting going on in some of these programs.

Each instance of a program generates a different output file.  In order
to parse these output files and aggregate their results, there are more
meta-programs.  The programs typically follow the naming convention
`*parse*.py`.

#### Estimating probability of routing failure and forwarding table state

There are two programs for estimating results instead of
computing/simulating results, `bound_res.py` and `bound_state.py`.  The
`bound_res.py` program can approximate the expected probability of routing failure
given a topology and level of resilience for both edge and vertex
failures.  This program was used to generate the figures plotting the
approximated probability of routing failure in the papers mentioned
above.

The `bound_state.py` contains preliminary approximations of the routing
state consumed by failure identifying resilience.  However, this
approximation was never that accurate in practice and thus may not be
valuable.

## Individual Program Descriptions

`bitweave.py`: An implementation of the Bit Weaving algorithm for the
table format used by `resnet_alg.py`.  Interfaces with `suri.py`.

`bound_res.py`: Approximate the probability of routing failure for a
topology.

`bound_state.py`: Approximate the total state required for resilience.
Not accurate.

`max_trees.py`:  Print the total number of trees possible given a
topology.

`myjsone.py`:  I didn't like the formatting of the default ijson
exporter.  This one makes prettier looking forwarding tables.

`priority_dict.py`:  A publicly available Python implementation of a
heap-based priority dictionary.

`resnet_alg.py`: The main program for computing state and generating
forwarding tables for failure identifying resilience.

`resnet_dfr.py`: A copy+pasted version of `resnet_alg.py` generated to
compute the number of virtual channels used to break dependencies
between FI resilient routes that are otherwise not restricted.  This is
necessary because it ensures that a single route never uses the same
port twice to avoid self-cycles and a single flow that could cause
deadlock.

`resnet_throughput.py`: The main program for computing throughput and
probability of routing failure for failure identifying resilience.

`res-sim_igraph-0.6.5.patch`: A patch for igraph-0.6.5 that adds
randomization to some of the underlying graph traversal algorithms.

`run_adst.py`: Compute the state (and generate forwarding
tables?) for ADST resilience.

`run_adst_throughput.py`: Compute throughput and the probability of
routing failure for ADST resilience.

`run_dfr.py`: Compute the state (and generate forwarding tables?) for
deadlock-free failure identifying resilience (Plinko).  Avoids
self-cycles.

`run_edst_line.py`: Copy+Pasted slightly different version of
`run_edst.py` generated because the line2 TTG was a late addition.

`run_edst_line_throughput.py`: Copy+Pasted slightly different version of
`run_edst_throughput.py` generated because the line2 TTG was a late
addition.

`run_edst.py`: Compute the state (and generate forwarding tables?) for
EDST resilience.

`run_edst_rand.py`: The random and max-dag TTGs were also late
additions? More copy+paste.

`run_edst_throughput.py`: Compute throughput and the probability of
routing failure for EDST resilience.

`run_edst_throughput_rand.py`: Copy+paste again for random and max-dag
TTGs.

`run_missing.sh`: Old file for finding and running missing (killed)
state files for failure identifying resilience initially generated by
`run_sim.sh`.

`run_sim.sh`: Run `resnet_alg.py` multiple times.

`run_throughput.py`: Run `resnet_throughput.py` multiple times.

`suri.py`: Chad R. Meiners reference implementation of 1-dimensional
weighted prefix minimization in Python from
[https://www.cse.msu.edu/~meinersc/suri.py](https://www.cse.msu.edu/~meinersc/suri.py)

`tree_alg.py`: The main program for computing state and generating
forwarding tables for disjoint tree resilience.

`tree_throughput.py`: The main program for computing throughput and
probability of routing failure for EDST and ADST resilience.

`dfr_output/parse_dfr_tail.py`: Self-described as 'Parse the output for
DFR generated by "tail -n 1 B*/*.yaml > file".'

`fail_output/fail_parse.py`: Parse in aggregate the output files and
throughput results.

`fail_output/plot_prob_fail.py`:  Plot some of the aggregated results.
More of these plotting scripts should be in this repo.  If they are not
added and you want them, you should bug me to find them and add them.

`output/find_missing.py`: Find out which files are missing.

`output/plot_tcam_sizes.py`: Another plotting file.

`output/tcam_state.py`: Parse the aggregate output of `run_sim.sh`

`output/yaml_loader.py`: Obsolete parsing script?

`topo/cch2yaml.py`: Convert files in the cch format into my silly YAML
format.

`topo/factorize.py`: Internet implementations of some factorization
algorithms.

`topo/topo_gen.py`: Generate topologies.  Supports EGFT, HyperX, and
Jellyfish.

`topo/topo_opt.py`: Find the instance of EGFT and HyperX topologies that
contain the fewest number of switches possible given a number of hosts,
switch radix, and bisection bandwidth.

`tree_fail_output/plot_fail_output.py`:  Plot throughput and probability
of failure.

`tree_fail_output/tree_fail_parse.py`: Parse the output of `run_*dst_throughput.py`.

`tree_output/expected_state.py`: Compute the expected state required by
different EDST and ADST resilience.  Should be accurate.

`tree_output/parse_tree_state.py`: Parse the output of `run_*dst.py`.

`tree_output/plot_tree_state.py`: Plot state data.

