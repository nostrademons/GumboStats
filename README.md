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

## Summary Results

The standard caveat on benchmarks applies: many of the speed numbers are
approximate, there is significant noise in these, and you should benchmark the
actual programs you intend to run on the actual hardware you intend to run them
on.  These were done on an Intel Core i5-3230M with 4 cores (only one running
the benchmarks, though, since they aren't multithreaded), running Ubuntu 14.10.

tl;dr summary:

* The corpus contains about 60K documents, median length 49K, max 1M.
* With the arena branch (1.0.0 candidate), the median document took just under 3ms to parse and 720k memory used.  There is a long tail, with the 95th percentile at 12ms and 2.4M.  Progression by version:
  * v0.9.1: 5.3ms, 163K used.
  * v0.9.2: 3.9ms, 163K used.
  * v0.9.3: 3.8ms, 173K used.
  * v0.10.0: 3.5ms, 208K used.
  * Using realloc & other memory fixes: 3.3ms, 215K used.
  * arena: 2.9ms, 720k used.
  * gumbo_libxml: 3.1ms, memory used is the same as libxml.
* Traversal time is a tiny fraction (~1-2%) of parsing time.  This should reassure anyone worried about converting the GumboNode tree to their own data structures.
* Changing the default buffer & vector sizes is a big win on memory, while being a wash on CPU.  Changing attributes from 4 >= 1 and stringbuffers from 10 >= 3 resulted in a reduction in median high-water-mark memory usage from 200K => 140K, with indistinguishable parse time.  Changing to attributes=0 reduced this further to 100K, with a slight increase in CPU time from additional reallocs.  * Adding a gumbo_stringbuffer_clear method instead of repeated init/destroy calls is another big win, saving roughly 5% on CPU and 10% on total bytes allocated.
* Moving ownership of temporary buffers over to the final parse tree instead of doing a fresh allocation & copying was a big loss, costing about 5% in CPU, 25% in memory, and 50% in total bytes allocated.  The reason is that most strings in HTML documents are 1-2 characters long, so replacing them with a raw temporary buffer that starts at 3 characters and doubles ends up allocating much more.  (It works well with arenas, though, where an arena that's freed and one that is not have the same memory usage.)
* Eliminating configurable memory allocators has no significant effect on performance.  Apparently the indirection of going through a function pointer is negligible.  (Some time in the debugger seems to indicate that gcc can inline the default memory allocation functions since they're defined in the same compilation unit and never reset during parsing.)
* Using realloc instead of malloc for growable buffers has limited effect.  With glibc malloc, the parser can re-use the same block of memory only about 10% of the time.  When it can, the savings are substantial (measured at ~75%, probably because re-use is more common with large blocks of memory).  However, newer mallocs like tcmalloc or jemalloc basically can't re-use anything, because they use a series of object pools that are sized as powers of two, so resizing a buffer automatically forces it into the next pool.  With jemalloc, there were a grand total of 6 successful reallocs in the corpus of 60,000 documents.
* Arenas drastically reduce parsing time, but at the cost of increased memory usage.  In typical use, Gumbo allocates about 2x the memory of the final parse tree over the course of parsing.  This is the lower bound on effective arena memory usage; however, because arenas are allocated in large chunks, it's often more than that (we use a default of 800K, which is roughly 4x the baseline v0.9.3 memory usage).  Because the absolute numbers on memory usage are so low, however, I believe this is a good trade-off.

## Result formatting

More detailed notes & explanations of how the results are formatted.

    num_nodes: mean=1737.38, median=1231.00, 95th%=4843.00, max=91858.00
    parse_time: mean=4182.78, median=2860.00, 95th%=11836.10, max=142205.00
    traversal_time: mean=61927.35, median=36000.00, 95th%=188000.00, max=3493000.00

Parse time is in microseconds, traversal time is in nanoseconds (because it was
too small to register otherwise).  The average document takes about 3ms to
parse, with the 95th percentile latency at about 12ms and a long tail beyond
that.  Traversal of the parse tree is about 2 orders of magnitude faster,
roughly 36us for the median document.

    allocations: mean=19782.47, median=14190.00, 95th%=55512.45, max=805162.00
    bytes_allocated: mean=697919.74, median=498341.00, 95th%=1962711.40,
    max=50036916.00
    high_water_mark: mean=572190.85, median=204060.00, 95th%=832980.15,
    max=4294967294.00

These are memory allocator stats, measured in bytes.  The 'high water mark' is
the greatest instantaneous heap usage measured by the allocator (note that since
many malloc implementations use object pools, this is often different from what
the OS reports).  These numbers are for v0.10.0 plus a patch or two; the arena
implementation gives round numbers where everything is a multiple of
ARENA_CHUNK_SIZE.

    num_nodes / doc_length: mean=27.61, median=26.66, 95th%=44.51, max=240.00
    parse_time / doc_length: mean=61.37, median=58.38, 95th%=87.22, max=434.88
    traversal_time / num_nodes: mean=32.92, median=29.41, 95th%=54.72, max=1325.58
    bytes_allocated / high_water_mark: mean=1.00, median=1.00, 95th%=1.00, max=1.00

These are key ratios.  doc_length is in units of a kilobyte to make the numbers
easier to read, parse_time is in microseconds/K, traversal_time is in
nanoseconds/node.  As a very rough estimate, for each K of document length,
it'll generate about 27 nodes, take 60us to parse, 1us to traverse, and
allocate about 10K.

    children: total=33060376, max=130
    8161441 22662277 2234792 1003 20 520 8 191 3 39 5 20 2 9 3 8
    0 0 0 1 1 1 1 1 1 1 39

    text: total=227410, max=8522
    70865 106986 15425 16247 15676 420 226 106 46 99 122 93 125 90 68 60
    0 0 0 0 1 1 1 1 2 3

    attribute: total=10658926, max=11
    10614778 40945 1811 703 590 97 1 0 0 0 1
    0 0 0 0 0 0 0 0 0 0 5

    attribute_name: total=54281, max=18
    0 28 8071 10557 25612 7924 1185 456 131 87 30 196 0 1 0 1
    1 2 3 3 4 4 4 4 4 5

    attribute_value: total=1527803, max=399
    1475279 3173 3765 8236 5134 6318 7624 3410 4649 821 757 554 931 390 343 858
    0 0 0 0 0 0 0 0 0 0 308

These are histograms of the number of children per node, size of text nodes
(also including doctype strings), number of attributes per node, size of
attribute names, and size of attribute values.  The first line is some basic
statistical information, including the total number of samples and the maximum
value.  The second line contains absolute counts for the first 16 bins in the
distribution, so eg. about 8 million nodes had no children at all, 22 million
had one, etc.  The third line are cumulative deciles (the first being the '0th
decile', i.e. all samples can fit in it); for example, 10% of attribute names
can fit in 2-character buffer, 80% can fit in a 4 characters, 90% in 5
characters, but to get to 100% you need an 18-character buffer.
