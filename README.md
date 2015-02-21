# GumboStats
Simple Python tool to collect stats on DOM shape and memory usage for Gumbo over a large corpus of HTML files

This is composed of a small C library that runs Gumbo over a document with a
custom allocator and tree-traversal, together with Python ctypes bindings for it
and a driver script that runs it over a CommonCrawl segment and aggregates
statistics.  Its purpose is to drive optimization decisions for Gumbo.

## Building/running

To build the C shared library:

  gcc gumbo_stats.c -std=c99 -Wall -fpic -shared -o libgumbostats.so \
    `pkg_config --cflags --libs gumbo`

(We don't use automake or a build system because it's overkill for a single-file
library that's only for information-gathering code.)

Then run the Python script from the same directory, under Python2.7:

  python gumbo_stats.py testdata/sample3.warc.gz 

If the extension of the input file is 'warc.gz', it's assumed to be a WARC (Web Archive) file of the sort CommonCrawl or wget uses.  Otherwise, it's assumed to be a single HTML document.

## Results

tl;dr summary:

* 

These are sample results on one segment of the CommonCrawl corpus, ~100K
documents, with explanation:

    num_nodes: mean=1704.98, median=1204.00, 95th%=4800.15, max=91858.00
    parse_time: mean=4936.51, median=3395.50, 95th%=14145.60, max=167992.00
    traversal_time: mean=84623.32, median=49000.00, 95th%=281000.00, max=3910000.00

Parse time is in microseconds, traversal time is in nanoseconds (because it was
too small to register otherwise).  The average document takes about 3.4ms to
parse, with 95th percentile latency at about 14ms and a long tail beyond that.
Traversal of the parse tree is about 2 orders of magnitude faster, roughly 50us
for the median document.

    allocations: mean=19782.47, median=14190.00, 95th%=55512.45, max=805162.00
    bytes_allocated: mean=697919.74, median=498341.00, 95th%=1962711.40,
    max=50036916.00
    high_water_mark: mean=572190.85, median=204060.00, 95th%=832980.15,
    max=4294967294.00

These are memory allocator stats, measured in bytes.  The 'high water mark' is
the greatest instantaneous heap usage measured by the allocator (note that since
many malloc implementations use object pools, this is often different from what
the OS reports).  The median document allocates about 500K, of which about 200K
is in use at any given time (much of the rest consists of vector/stringbuffer
resizes).  There's a long tail, but the 95th percentile is at around 2M in
allocations.

    num_nodes / doc_length: mean=27.36, median=26.56, 95th%=44.64, max=240.00
    parse_time / doc_length: mean=73.73, median=69.70, 95th%=111.69, max=561.85
    traversal_time / num_nodes: mean=47.40, median=41.67, 95th%=81.80, max=12600.00
    bytes_allocated / high_water_mark: mean=2.38, median=2.38, 95th%=2.76, max=7.20
    high_water_mark / doc_length: mean=7545.54, median=4411.77, 95th%=6853.25,
    max=72796055.78
    bytes_allocated / doc_length: mean=10779.40, median=10571.60, 95th%=15134.17,
    max=308869.85

These are key ratios.  doc_length is in units of a kilobyte to make the numbers
easier to read, parse_time is in microseconds/K, traversal_time is in
nanoseconds/node.  As a very rough estimate, for each K of document length,
it'll generate about 27 nodes, take 70us to parse, 1us to traverse, and
allocate about 10K, about 5K of which is still in use after parsing completes.

    children: mean=254310.58, median=0.00, 95th%=30.45, max=22662277.00
    8161441 22662277 2234792 1003 20 520 8 191 3 39 5 20 2 9 3 8
    0 0 0 1 1 1 1 1 1 1 39

    text: mean=26.69, median=0.00, 95th%=0.00, max=106986.00
    70865 106986 15425 16247 15676 420 226 106 46 99 122 93 125 90 68 60
    0 0 0 0 1 1 1 1 2 3

    attribute: mean=968993.27, median=97.00, 95th%=5327861.50, max=10614778.00
    10614778 40945 1811 703 590 97 1 0 0 0 1
    0 0 0 0 0 0 0 0 0 0 5

    attribute_name: mean=3015.61, median=58.50, 95th%=12815.25, max=25612.00
    0 28 8071 10557 25612 7924 1185 456 131 87 30 196 0 1 0 1
    1 2 3 3 4 4 4 4 4 5 17

    attribute_value: mean=3829.08, median=0.00, 95th%=241.40, max=1475279.00
    1475279 3173 3765 8236 5134 6318 7624 3410 4649 821 757 554 931 390 343 858
    0 0 0 0 0 0 0 0 0 0 308

These are histograms of the number of children per node, size of text nodes
(also including doctype strings), number of attributes per node, size of
attribute names, and size of attribute values.  The first line is some basic
statistical information; in this case, it just confirms what we suspected, that
the distributions are very long-tail power-laws.  The second line contains
absolute counts for the first 16 bins in the distribution, so about 8 million
nodes had no children at all, 22 million had one, etc.  The third line are
cumulative deciles (actually 9% increments); for example, 18% of attribute names
can fit in 2-character buffer, 45% can fit in a 4 characters, 82% in 5
characters, but to get to 91% you need a 17-character buffer, and 100% would be
25,612.
