# GumboStats
Simple Python tool to collect stats on DOM shape and memory usage for Gumbo over a large corpus of HTML files

This is composed of a small C library that runs Gumbo over a document with a
custom allocator and tree-traversal, together with Python ctypes bindings for it
and a driver script that runs it over a CommonCrawl segment and aggregates
statistics.  Its purpose is to drive optimization decisions for Gumbo.
